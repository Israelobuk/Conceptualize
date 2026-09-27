from shop.stock import reserve
from shop.reconciliation import stock_event
import pytest


def test_reservation_contract_and_consumer():
    result=reserve(10,3)
    assert result.remaining==7 and result.reserved==3
    assert stock_event(10,3)=={'remaining':7,'reserved':3}
    with pytest.raises(ValueError):reserve(2,3)
