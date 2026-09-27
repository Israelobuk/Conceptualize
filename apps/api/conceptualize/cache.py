import json
import logging
from time import monotonic

import redis

from .config import settings

log = logging.getLogger(__name__)


class RuntimeCache:
    def __init__(self, url: str):
        self.retry_after = 0.0
        self.redis = redis.Redis.from_url(
            url, socket_connect_timeout=0.2, socket_timeout=0.2, decode_responses=True
        )

    def get(self, key: str) -> dict | None:
        if monotonic() < self.retry_after:
            return None
        try:
            raw = self.redis.get(key)
            result = json.loads(raw) if raw else None
            if result is not None and not isinstance(result, dict):
                return None
            return result
        except redis.RedisError:
            self.retry_after = monotonic() + 5
            log.warning("Redis read unavailable; executing runtime without cache")
            return None
        except (ValueError, TypeError):
            log.warning("Invalid cached JSON; executing runtime without cache")
            return None

    def set(self, key: str, value: dict, ttl: int = 300):
        if monotonic() < self.retry_after:
            return
        try:
            self.redis.setex(key, ttl, json.dumps(value))
        except redis.RedisError:
            self.retry_after = monotonic() + 5
            log.warning("Redis write unavailable; context result remains usable")
        except (ValueError, TypeError):
            log.warning("Context result cannot be cached; result remains usable")


cache = RuntimeCache(settings.redis_url)
