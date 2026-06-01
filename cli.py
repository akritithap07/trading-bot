import argparse
import sys
import time
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from bot.validators import (
    validate_symbol, validate_side, validate_order_type,
    validate_quantity, validate_price, validate_target_price,
    ValidationError,
)
from bot.orders import place_order, check_risk, RISK_DEVIATION_THRESHOLD
from bot.client import BinanceClientError, BinanceClient
from bot.logging_config import setup_logger

console = Console()
logger  = setup_logger()


# ─────────────────────────────────────────────
#  Display helpers
# ─────────────────────────────────────────────

def print_banner():
    console.print(Panel(
        "[bold yellow]🤖  Binance Futures Trading Bot[/bold yellow]\n"
        "[dim]Testnet  |  Not real money[/dim]",
        box=box.DOUBLE_EDGE,
        expand=False,
    ))


def print_order_summary(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float],
    dry_run: bool = False,
    live_price: Optional[float] = None,
):
    title = "[yellow]⚡ DRY RUN — Order Preview[/yellow]" if dry_run else "Order Request"
    table = Table(box=box.ROUNDED, show_header=False, title=title)
    table.add_column("Field", style="bold cyan", min_width=16)
    table.add_column("Value", style="white")

    side_fmt = f"[green]{side}[/green]" if side == "BUY" else f"[red]{side}[/red]"

    table.add_row("Symbol",   symbol)
    table.add_row("Side",     side_fmt)
    table.add_row("Type",     order_type)
    table.add_row("Quantity", str(quantity))

    if price:
        table.add_row("Order Price", f"{price:,.2f} USDT")
    if live_price:
        table.add_row("Live Market Price", f"{live_price:,.2f} USDT")
        if price:
            estimated_cost = round(price * quantity, 2)
        else:
            estimated_cost = round(live_price * quantity, 2)
        table.add_row("Estimated Cost", f"[bold]{estimated_cost:,.2f} USDT[/bold]")

    if dry_run:
        table.add_row("Status", "[yellow]SIMULATED — no order sent[/yellow]")

    console.print(table)


def print_order_result(result: dict):
    if result.get("dry_run"):
        console.print(
            Panel(
                f"[yellow]⚡ DRY RUN complete.[/yellow]\n"
                f"Estimated cost: [bold]{result.get('estimated_cost', 'N/A'):,} USDT[/bold]\n"
                f"Live price used: {result.get('live_price', 'N/A'):,} USDT\n\n"
                "[dim]No order was placed on the exchange.[/dim]",
                title="Simulation Result",
                box=box.ROUNDED,
            )
        )
        return

    table = Table(box=box.ROUNDED, show_header=False, title="✅ Order Placed")
    table.add_column("Field", style="bold cyan", min_width=16)
    table.add_column("Value", style="white")

    status = result.get("status", "N/A")
    status_fmt = f"[green]{status}[/green]" if status == "FILLED" else f"[yellow]{status}[/yellow]"

    table.add_row("Order ID",     str(result.get("orderId",     "N/A")))
    table.add_row("Status",       status_fmt)
    table.add_row("Executed Qty", str(result.get("executedQty", "0")))
    avg = result.get("avgPrice") or result.get("price", "N/A")
    table.add_row("Avg Price",    str(avg))
    table.add_row("Symbol",       str(result.get("symbol",      "N/A")))

    console.print(table)


def handle_risk_warning(
    symbol: str,
    order_type: str,
    price: Optional[float],
) -> Optional[float]:
    """
    Fetch live price, show cost estimate, warn if deviation is high.
    Returns live_price or None on failure.
    """
    try:
        live_price, deviation = check_risk(symbol, order_type, price)
    except BinanceClientError as e:
        console.print(f"[dim]⚠ Could not fetch live price: {e}[/dim]")
        return None

    if deviation is not None and abs(deviation) > RISK_DEVIATION_THRESHOLD:
        direction = "above" if deviation > 0 else "below"
        console.print(
            Panel(
                f"[bold red]⚠  RISK WARNING[/bold red]\n\n"
                f"  Live market price : [cyan]{live_price:,.2f} USDT[/cyan]\n"
                f"  Your order price  : [yellow]{price:,.2f} USDT[/yellow]\n"
                f"  Deviation         : [bold red]{deviation:+.1f}% {direction} market[/bold red]\n\n"
                f"[dim]This order is significantly away from the current market price.\n"
                f"For LIMIT orders this may take a long time to fill or never fill.[/dim]",
                box=box.HEAVY,
                border_style="red",
            )
        )
        confirm = console.input("[bold red]Proceed anyway? (y/n):[/bold red] ").strip().lower()
        if confirm != "y":
            console.print("[dim]Order cancelled by user.[/dim]")
            logger.info(f"Order cancelled by user after risk warning | symbol={symbol} deviation={deviation}%")
            sys.exit(0)

    return live_price


# ─────────────────────────────────────────────
#  Watch mode
# ─────────────────────────────────────────────

def run_watch_mode(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    target_price: float,
    price: Optional[float],
    dry_run: bool,
    poll_interval: int = 5,
):
    client = BinanceClient()
    direction = "falls to" if side == "BUY" else "rises to"

    console.print(Panel(
        f"[bold cyan]👁  Watch Mode Active[/bold cyan]\n\n"
        f"  Symbol       : [yellow]{symbol}[/yellow]\n"
        f"  Side         : {'[green]' + side + '[/green]' if side == 'BUY' else '[red]' + side + '[/red]'}\n"
        f"  Target price : [bold]{target_price:,.2f} USDT[/bold] ({direction})\n"
        f"  Quantity     : {quantity}\n"
        f"  Polling      : every {poll_interval}s\n\n"
        "[dim]Ctrl+C to cancel.[/dim]",
        box=box.ROUNDED,
    ))

    logger.info(
        f"Watch mode started | symbol={symbol} side={side} "
        f"target={target_price} qty={quantity}"
    )

    try:
        while True:
            current_price = client.get_price(symbol)

            triggered = (
                (side == "BUY"  and current_price <= target_price) or
                (side == "SELL" and current_price >= target_price)
            )

            status_color = "[green]" if triggered else "[cyan]"
            console.print(
                f"  {status_color}{'▶' if triggered else '◉'}[/]  "
                f"{symbol}  Current: [bold]{current_price:,.2f}[/bold]  "
                f"Target: {target_price:,.2f}  "
                f"Gap: {current_price - target_price:+,.2f}"
            )

            if triggered:
                console.print(f"\n[bold green]🎯 Target price hit! Placing order...[/bold green]\n")
                logger.info(
                    f"Watch mode triggered | symbol={symbol} "
                    f"current={current_price} target={target_price}"
                )

                result = place_order(symbol, side, order_type, quantity, price, dry_run)
                print_order_result(result)

                if dry_run:
                    console.print("[yellow]⚡ Dry run — no real order sent.[/yellow]")
                else:
                    console.print("[bold green]✅ Order placed successfully![/bold green]")
                break

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        console.print("\n[dim]Watch mode cancelled by user.[/dim]")
        logger.info("Watch mode cancelled by user (KeyboardInterrupt)")
        sys.exit(0)


# ─────────────────────────────────────────────
#  Interactive mode
# ─────────────────────────────────────────────

def interactive_mode():
    print_banner()
    console.print("\n[bold]Welcome! Let's place an order interactively.[/bold]\n")

    console.print("[cyan]Supported symbols:[/cyan] BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT")
    symbol_input     = console.input("[bold]Symbol:[/bold] ").strip()
    side_input       = console.input("[bold]Side (BUY/SELL):[/bold] ").strip()
    order_type_input = console.input("[bold]Order type (MARKET/LIMIT):[/bold] ").strip()
    quantity_input   = console.input("[bold]Quantity:[/bold] ").strip()

    price_input = None
    if order_type_input.upper() == "LIMIT":
        price_input = console.input("[bold]Limit price (USDT):[/bold] ").strip()

    watch_input       = console.input("[bold]Enable watch mode? (y/n):[/bold] ").strip().lower()
    target_price_input = None
    if watch_input == "y":
        target_price_input = console.input("[bold]Target price to trigger order:[/bold] ").strip()

    dry_run_input = console.input("[bold]Dry run (simulate only)? (y/n):[/bold] ").strip().lower()
    dry_run       = dry_run_input == "y"

    try:
        symbol       = validate_symbol(symbol_input)
        side         = validate_side(side_input)
        order_type   = validate_order_type(order_type_input)
        quantity     = validate_quantity(quantity_input)
        price        = validate_price(price_input, order_type)
        target_price = validate_target_price(target_price_input)
    except ValidationError as e:
        console.print(f"[bold red]❌ Validation Error:[/bold red] {e}")
        sys.exit(1)

    live_price = handle_risk_warning(symbol, order_type, price)

    print_order_summary(symbol, side, order_type, quantity, price, dry_run, live_price)

    confirm = console.input("\n[yellow]Confirm? (y/n):[/yellow] ").strip().lower()
    if confirm != "y":
        console.print("[dim]Cancelled.[/dim]")
        sys.exit(0)

    if target_price:
        run_watch_mode(symbol, side, order_type, quantity, target_price, price, dry_run)
        return

    try:
        result = place_order(symbol, side, order_type, quantity, price, dry_run)
        print_order_result(result)
        if not dry_run:
            console.print("[bold green]✅ Order placed successfully![/bold green]")
    except BinanceClientError as e:
        console.print(f"[bold red]❌ Order Failed:[/bold red] {e}")
        logger.error(f"Order failed: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
#  Direct CLI mode
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🤖 Binance Futures Trading Bot (Testnet)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.01 --price 50000\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01 --dry-run\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01 --watch --target-price 60000\n"
        ),
    )

    parser.add_argument("--symbol", required=True, help="Trading pair e.g. BTCUSDT")
    parser.add_argument("--side", required=True, help="BUY or SELL")
    parser.add_argument("--type", required=True, dest="order_type", help="MARKET or LIMIT")
    parser.add_argument("--quantity", required=True, help="Order quantity e.g. 0.01")
    parser.add_argument("--price", required=False, default=None,
                        help="Limit price (required for LIMIT)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate order without placing it")
    parser.add_argument("--watch", action="store_true",
                        help="Watch price and auto-trigger order")
    parser.add_argument("--target-price", required=False, default=None,
                        dest="target_price",
                        help="Price at which to trigger order (used with --watch)")

    args = parser.parse_args()

    print_banner()

    # Validate all inputs
    try:
        symbol       = validate_symbol(args.symbol)
        side         = validate_side(args.side)
        order_type   = validate_order_type(args.order_type)
        quantity     = validate_quantity(args.quantity)
        price        = validate_price(args.price, order_type)
        target_price = validate_target_price(args.target_price)

    except ValidationError as e:
        console.print(f"[bold red]❌ Validation Error:[/bold red] {e}")
        logger.warning(f"Validation failed: {e}")
        sys.exit(1)

    # NEW LOGGING BLOCK (ADDED)
    logger.info(
        f"CLI COMMAND | "
        f"symbol={symbol} | "
        f"side={side} | "
        f"type={order_type} | "
        f"qty={quantity} | "
        f"price={price} | "
        f"dry_run={args.dry_run} | "
        f"watch={args.watch}"
    )

    if args.watch and target_price is None:
        console.print("[bold red]❌ --watch requires --target-price[/bold red]")
        logger.warning("--watch used without --target-price")
        sys.exit(1)

    # Risk warning + live price fetch
    live_price = handle_risk_warning(symbol, order_type, price)

    # Show summary
    print_order_summary(
        symbol,
        side,
        order_type,
        quantity,
        price,
        args.dry_run,
        live_price,
    )

    # Watch mode
    if args.watch:
        run_watch_mode(
            symbol,
            side,
            order_type,
            quantity,
            target_price,
            price,
            args.dry_run,
        )
        return

    # Place order
    try:
        result = place_order(
            symbol,
            side,
            order_type,
            quantity,
            price,
            args.dry_run,
        )

        print_order_result(result)

        if not args.dry_run:
            console.print("[bold green]✅ Order placed successfully![/bold green]")

        logger.info("CLI session completed successfully")

    except BinanceClientError as e:
        console.print(f"[bold red]❌ Order Failed:[/bold red] {e}")
        logger.error(f"Order placement failed: {e}")
        sys.exit(1)
    
    logger.info(
        "CLI command received",
        extra={
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
        }
    )


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_mode()
    else:
        main()