from .names import canonical
def ledger_key(name):
    return "account:" + canonical(name)
