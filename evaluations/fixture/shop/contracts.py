from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    order_id: str
    total: float
