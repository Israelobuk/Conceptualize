from .records import decode
def status(record):
    return "enabled" if decode(record)[1] else "disabled"
