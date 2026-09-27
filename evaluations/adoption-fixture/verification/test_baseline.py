from relay.gateway import submit
from relay.admission import admit
from relay.bootstrap import worker_options
from relay.directory import lookup
from relay.adapter import send_notification
from relay.store import save, load
from relay.reporting import status
from relay.routes import route

def test_delivery():
    assert submit("x", 12) == {"id": "x", "bytes": 12}
def test_configuration():
    assert admit(1) and not admit(0)
    assert "maximum_batch" in worker_options()
def test_directory():
    assert lookup(" A ", {"a": 1}) == 1
def test_dispatch():
    assert send_notification(lambda: "ok") == "ok"
def test_persistence():
    assert load(save("x", True)) == ("x", True)
    assert status(save("x", False)) == "disabled"
def test_routes():
    assert route(" Hello World ") == "/messages/hello-world"
