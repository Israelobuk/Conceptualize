from .customer_keys import key


def customer_bucket(email):
    return key(email)
