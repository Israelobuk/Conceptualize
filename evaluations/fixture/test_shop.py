from shop.checkout import checkout
from shop.orders import place_order
from shop.refunds import can_refund
from shop.notifications import notify


def test_checkout():
    assert checkout('a', 12.5).total == 12.5


def test_audit():
    assert place_order('a', 12.5) == {'order':'a','dollars':12.5}


def test_roles():
    assert can_refund('admin')
    assert not can_refund('reader')


def test_notifications():
    assert notify('a') == 'sent:a'
