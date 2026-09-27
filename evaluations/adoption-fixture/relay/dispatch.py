from .retry import run
def dispatch(attempt):
    return run(attempt)
