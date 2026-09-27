from .settings import ORDER_LIMIT


def accept_batch(units):
    return isinstance(units,int) and 1 <= units <= ORDER_LIMIT
