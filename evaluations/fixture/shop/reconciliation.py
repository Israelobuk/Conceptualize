from .stock import reserve


def stock_event(stock,units):
    return {'remaining':reserve(stock,units),'reserved':units}
