from shop import notifications


def test_timeout_retries(monkeypatch):
    calls=[]
    def flaky(order):
        calls.append(order)
        if len(calls)<3:
            raise TimeoutError('transient')
        return 'sent:'+order
    monkeypatch.setattr(notifications,'send',flaky)
    assert notifications.notify('a') == 'sent:a'
    assert len(calls)==3


def test_nontransient_not_retried(monkeypatch):
    import pytest
    calls=[]
    def invalid(order):
        calls.append(order)
        raise ValueError('invalid')
    monkeypatch.setattr(notifications,'send',invalid)
    with pytest.raises(ValueError):
        notifications.notify('a')
    assert len(calls)==1
