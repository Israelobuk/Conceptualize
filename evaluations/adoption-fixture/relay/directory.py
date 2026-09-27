from .names import canonical
def lookup(name, values):
    return values.get(canonical(name))
