from typing import Optional

VALID_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
VALID_SIDES = ["BUY", "SELL"]
VALID_ORDER_TYPES = ["MARKET", "LIMIT"]


class ValidationError(Exception):
    pass


def validate_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol not in VALID_SYMBOLS:
        raise ValidationError(
            f"Invalid symbol '{symbol}'. Supported: {', '.join(VALID_SYMBOLS)}"
        )
    return symbol


def validate_side(side: str) -> str:
    side = side.upper().strip()
    if side not in VALID_SIDES:
        raise ValidationError(f"Side must be BUY or SELL, got '{side}'")
    return side


def validate_order_type(order_type: str) -> str:
    order_type = order_type.upper().strip()
    if order_type not in VALID_ORDER_TYPES:
        raise ValidationError(
            f"Order type must be MARKET or LIMIT, got '{order_type}'"
        )
    return order_type


def validate_quantity(quantity: str) -> float:
    try:
        qty = float(quantity)
        if qty <= 0:
            raise ValidationError("Quantity must be greater than 0")
        return round(qty, 3)
    except ValueError:
        raise ValidationError(f"Invalid quantity '{quantity}' — must be a number")


def validate_price(price: Optional[str], order_type: str) -> Optional[float]:
    if order_type == "LIMIT":
        if price is None:
            raise ValidationError("Price is required for LIMIT orders")
        try:
            p = float(price)
            if p <= 0:
                raise ValidationError("Price must be greater than 0")
            return round(p, 2)
        except ValueError:
            raise ValidationError(f"Invalid price '{price}' — must be a number")
    return None


def validate_target_price(target_price: Optional[str]) -> Optional[float]:
    if target_price is None:
        return None
    try:
        p = float(target_price)
        if p <= 0:
            raise ValidationError("Target price must be greater than 0")
        return round(p, 2)
    except ValueError:
        raise ValidationError(
            f"Invalid target price '{target_price}' — must be a number"
        )