from relay.contracts import Delivery
from relay.publish import publish
from relay.gateway import submit
import pytest
def test_contract():
    assert Delivery("x", 12).byte_count == 12
    assert not hasattr(Delivery("x", 12), "size")
    assert submit("x", 12) == {"id": "x", "bytes": 12}
    for value in [-1, 2.5, True, "12"]:
        with pytest.raises((ValueError, TypeError)):
            publish("x", value)
