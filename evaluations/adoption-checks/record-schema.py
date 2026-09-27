from relay.store import save, load
from relay.reporting import status
import pytest
def test_schema():
    assert save("x",True)=={"id":"x","version":2,"state":"enabled"}
    assert save("x",False)=={"id":"x","version":2,"state":"disabled"}
    assert load({"id":"x","active":True})==("x",True)
    assert status(save("x",False))=="disabled"
    for record in [{"id":"x","version":3,"state":"enabled"},{"id":"x","version":2,"state":"bad"}]:
        with pytest.raises(ValueError): load(record)
