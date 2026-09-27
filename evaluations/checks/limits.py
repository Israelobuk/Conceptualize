import pytest
from shop.inventory import validate_quantity
from shop.batch_gateway import accept_batch
from shop.settings import ORDER_LIMIT


def test_shared_limit():
    assert ORDER_LIMIT==25
    assert validate_quantity(25)==25
    assert accept_batch(25)
    assert not accept_batch(26)
    with pytest.raises(ValueError):validate_quantity(26)
    with pytest.raises(ValueError):validate_quantity(0)
