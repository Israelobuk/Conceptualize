from .dispatch import dispatch
def send_notification(attempt):
    return dispatch(attempt)
