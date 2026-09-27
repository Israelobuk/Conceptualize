from .shipping import shipping_price


def shipping_invoice(express=False):
    return {'shipping':shipping_price(express)}
