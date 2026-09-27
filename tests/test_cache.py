import redis
from conceptualize.cache import RuntimeCache


def test_failed_cache_backs_off_then_recovers(monkeypatch):
    import conceptualize.cache as module

    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0], raising=False)
    cache = RuntimeCache("redis://localhost:1/0")
    calls = []

    def unavailable(key):
        calls.append(key)
        raise redis.ConnectionError("offline")

    monkeypatch.setattr(cache.redis, "get", unavailable)
    monkeypatch.setattr(cache.redis, "setex", lambda *a: calls.append("set"))
    assert cache.get("one") is None
    cache.set("one", {"context": "valid"})
    assert cache.get("two") is None
    assert calls == ["one"]
    clock[0] += 6
    monkeypatch.setattr(cache.redis, "get", lambda key: '{"context":"recovered"}')
    assert cache.get("three") == {"context": "recovered"}


def test_invalid_cache_json_is_a_miss(monkeypatch):
    cache = RuntimeCache("redis://localhost:1/0")
    monkeypatch.setattr(cache.redis, "get", lambda key: "not json")
    assert cache.get("key") is None
