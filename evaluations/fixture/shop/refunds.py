from .auth import authenticate


def can_refund(token: str) -> bool:
    return authenticate(token).role == 'admin'
