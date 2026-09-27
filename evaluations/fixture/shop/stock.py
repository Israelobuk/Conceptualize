def reserve(stock,units):
    if units < 1 or units > stock:
        raise ValueError('invalid reservation')
    return stock-units
