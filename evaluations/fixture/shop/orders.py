from .checkout import checkout
from .warehouse import audit_row


def place_order(order_id: str, total: float) -> dict:
    return audit_row(checkout(order_id, total))
