def encode(identifier, active):
    return {"id": identifier, "active": bool(active)}
def decode(record):
    return record["id"], record["active"]
