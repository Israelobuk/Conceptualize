from relay.routes import route
import pytest
def test_routes():
    assert route(" --Hello__ WORLD!! ")=="/messages/hello-world"
    assert route("a---b")=="/messages/a-b"
    with pytest.raises(ValueError): route(" !!! ")
