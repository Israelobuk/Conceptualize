from dataclasses import dataclass
@dataclass(frozen=True)
class Delivery:
    message_id: str
    size: int
