from .settings import ORDER_LIMIT


def validate_quantity(units):
    if not isinstance(units,int) or units < 1 or units > ORDER_LIMIT:
        raise ValueError('invalid quantity')
    return units
