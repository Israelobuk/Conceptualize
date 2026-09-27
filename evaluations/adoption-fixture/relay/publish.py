from .contracts import Delivery
def publish(message_id, size):
    return Delivery(message_id, size)
