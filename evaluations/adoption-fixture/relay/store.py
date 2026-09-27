from .records import encode, decode
def save(identifier, active):
    return encode(identifier, active)
def load(record):
    return decode(record)
