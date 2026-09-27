import pytest
from shop.checkout import checkout
from shop.contracts import Receipt
from shop.orders import place_order
from shop.warehouse import audit_row


def test_integer_cents_contract():
    receipt=checkout('a',1250)
    assert isinstance(receipt,Receipt)
    assert receipt.amount_cents == 1250
    assert not hasattr(receipt,'total')


def test_consumer_keeps_dollars():
    assert audit_row(checkout('a',1250)) == {'order':'a','dollars':12.5}
    assert place_order('a',1250) == {'order':'a','dollars':12.5}


def test_validation():
    with pytest.raises(ValueError):
        checkout('a',-1)
    with pytest.raises((ValueError,TypeError)):
        checkout('a',1.5)
