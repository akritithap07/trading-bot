from typing import Optional
from bot.client import BinanceClient, BinanceClientError
from bot.logging_config import setup_logger

logger = setup_logger()

# Risk threshold — warn if order price deviates more than this % from market
RISK_DEVIATION_THRESHOLD = 10.0


def check_risk(
    symbol: str,
    order_type: str,
    price: Optional[float],
    client: Optional[BinanceClient] = None,
) -> tuple[float, Optional[float]]:
    """
    Fetch live market price and calculate deviation if a limit price is given.
    Returns (live_price, deviation_pct) — deviation is None for MARKET orders.

    Accepts an optional client instance to avoid creating multiple connections.
    """
    if client is None:
        client = BinanceClient()

    live_price = client.get_price(symbol)

    if order_type == "LIMIT" and price is not None:
        deviation = ((price - live_price) / live_price) * 100
        logger.debug(
            f"Risk check | symbol={symbol} live={live_price:.2f} "
            f"entered={price} deviation={deviation:.2f}%"
        )
        return live_price, round(deviation, 2)

    return live_price, None


def place_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    dry_run: bool = False,
) -> dict:
    """
    Place a MARKET or LIMIT order on Binance Futures.

    Args:
        symbol:     Trading pair e.g. BTCUSDT
        side:       BUY or SELL
        order_type: MARKET or LIMIT
        quantity:   Order size
        price:      Required for LIMIT orders
        dry_run:    If True, simulate without sending a real order

    Returns:
        dict with order details (or simulated result for dry_run)
    """
    # Single client instance reused across this order lifecycle
    client = BinanceClient()

    if dry_run:
        live_price     = client.get_price(symbol)
        estimated_cost = round(live_price * quantity, 2)
        logger.info(
            f"DRY RUN | {order_type} {side} {symbol} "
            f"qty={quantity} live_price={live_price} estimated_cost={estimated_cost} USDT"
        )
        return {
            "dry_run":        True,
            "symbol":         symbol,
            "side":           side,
            "type":           order_type,
            "quantity":       quantity,
            "price":          price or live_price,
            "live_price":     live_price,
            "estimated_cost": estimated_cost,
        }

    params: dict = {
        "symbol":   symbol,
        "side":     side,
        "type":     order_type,
        "quantity": quantity,
    }

    if order_type == "LIMIT":
        params["price"]       = price
        params["timeInForce"] = "GTC"   # Good Till Cancelled

    logger.info(
        f"Placing order | {order_type} {side} {symbol} qty={quantity}"
        + (f" price={price}" if price else "")
    )

    result = client.post("/fapi/v1/order", params)

    logger.info(
        f"Order success | orderId={result.get('orderId')} "
        f"status={result.get('status')} executedQty={result.get('executedQty')}"
    )

    return result