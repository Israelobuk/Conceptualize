from .settings import BATCH_LIMIT
def admit(count):
    return isinstance(count, int) and 0 < count <= BATCH_LIMIT
