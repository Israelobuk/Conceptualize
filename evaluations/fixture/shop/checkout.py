from .contracts import Receipt


def checkout(order_id: str, total: float) -> Receipt:
    if total < 0:
        raise ValueError('negative amount')
    return Receipt(order_id=order_id, total=total)
