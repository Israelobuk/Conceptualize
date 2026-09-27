from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str


def authenticate(token: str) -> Identity:
    if token == 'admin':
        return Identity('u1', 'admin')
    if token == 'reader':
        return Identity('u2', 'reader')
    raise ValueError('invalid token')
