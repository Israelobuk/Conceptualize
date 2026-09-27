from .transport import send


def notify(order_id: str) -> str:
    return send(order_id)
