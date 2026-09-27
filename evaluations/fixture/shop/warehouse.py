from .contracts import Receipt


def audit_row(receipt: Receipt) -> dict:
    return {'order': receipt.order_id, 'dollars': receipt.total}
