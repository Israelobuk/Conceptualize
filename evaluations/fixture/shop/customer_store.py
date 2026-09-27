from .customer_keys import key


def find_customer(email, records):
    return records.get(key(email))
