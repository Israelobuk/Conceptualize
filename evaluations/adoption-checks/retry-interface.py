from relay.adapter import send_notification
import pytest
def test_retry():
    calls=[]
    def attempt():
        calls.append(1)
        if len(calls)<3: raise TimeoutError()
        return "ok"
    assert send_notification(attempt)=="ok" and len(calls)==3
    calls.clear()
    def fatal():
        calls.append(1)
        raise RuntimeError("fatal")
    with pytest.raises(RuntimeError): send_notification(fatal)
    assert len(calls)==1
