from .settings import BATCH_LIMIT
def worker_options():
    return {"maximum_batch": BATCH_LIMIT}
