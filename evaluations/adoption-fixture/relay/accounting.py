from .contracts import Delivery
def charge(delivery: Delivery):
    return {"id": delivery.message_id, "bytes": delivery.size}
