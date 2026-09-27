import pytest
from shop.auth import authenticate
from shop.refunds import can_refund


def test_permissions_are_explicit():
    assert authenticate('admin').permissions == frozenset({'refund'})
    assert authenticate('reader').permissions == frozenset()
    assert not hasattr(authenticate('admin'),'role')


def test_refund_consumer():
    assert can_refund('admin')
    assert not can_refund('reader')
    with pytest.raises(ValueError):
        can_refund('invalid')
