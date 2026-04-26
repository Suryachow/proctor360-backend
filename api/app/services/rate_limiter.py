from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class InMemoryRateLimiter:
    """Simple per-key sliding-window limiter.

    This process-local limiter is suitable as a safe default and should be replaced
    by a distributed limiter (e.g. Redis) when scaling to multiple API replicas.
    """

    def __init__(self):
        self._buckets: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitDecision:
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_seconds)

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = int(max(1.0, (bucket[0] - cutoff).total_seconds()))
                return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=retry_after)

            bucket.append(now)
            remaining = max(0, limit - len(bucket))
            return RateLimitDecision(allowed=True, remaining=remaining, retry_after_seconds=0)


class RedisSlidingWindowRateLimiter:
    """Distributed per-key sliding-window limiter backed by Redis sorted sets."""

    _LUA_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local start_ms = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, '-inf', start_ms)
local count = redis.call('ZCARD', key)

if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry_after_ms = window_ms
  if oldest[2] ~= nil then
    retry_after_ms = math.max(1, window_ms - (now_ms - tonumber(oldest[2])))
  end
  return {0, 0, retry_after_ms}
end

redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms + 1000)
local remaining = limit - (count + 1)
return {1, remaining, 0}
"""

    def __init__(self, redis_url: str, prefix: str = "proctor:ratelimit"):
        self._prefix = prefix
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def _key(self, raw_key: str) -> str:
        return f"{self._prefix}:{raw_key}"

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitDecision:
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        window_ms = int(window_seconds * 1000)
        redis_key = self._key(key)
        member = f"{now_ms}:{uuid4().hex}"

        result = self._redis.eval(
            self._LUA_SCRIPT,
            1,
            redis_key,
            str(now_ms),
            str(window_ms),
            str(limit),
            member,
        )

        allowed = bool(int(result[0]))
        remaining = int(result[1])
        retry_after_ms = int(result[2])
        retry_after_seconds = max(0, int((retry_after_ms + 999) / 1000))

        return RateLimitDecision(
            allowed=allowed,
            remaining=remaining,
            retry_after_seconds=retry_after_seconds,
        )


class HybridRateLimiter:
    """Uses Redis limiter when available, falls back to in-memory limiter."""

    def __init__(self):
        self._fallback = InMemoryRateLimiter()
        self._redis_limiter: RedisSlidingWindowRateLimiter | None = None
        self._last_redis_error: str | None = None

        if settings.rate_limit_use_redis:
            try:
                self._redis_limiter = RedisSlidingWindowRateLimiter(
                    redis_url=settings.redis_url,
                    prefix=settings.rate_limit_redis_prefix,
                )
                self._redis_limiter._redis.ping()
            except RedisError:
                self._redis_limiter = None
                self._last_redis_error = "redis_unavailable"

    @property
    def using_redis(self) -> bool:
        return self._redis_limiter is not None

    @property
    def mode(self) -> str:
        return "redis" if self._redis_limiter is not None else "memory"

    @property
    def is_degraded(self) -> bool:
        return settings.rate_limit_use_redis and self._redis_limiter is None

    @property
    def last_redis_error(self) -> str | None:
        return self._last_redis_error

    def redis_healthy(self) -> bool:
        if self._redis_limiter is None:
            return False
        try:
            self._redis_limiter._redis.ping()
            return True
        except RedisError:
            return False

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitDecision:
        if self._redis_limiter is None:
            return self._fallback.allow(key=key, limit=limit, window_seconds=window_seconds)

        try:
            return self._redis_limiter.allow(key=key, limit=limit, window_seconds=window_seconds)
        except RedisError as exc:
            self._last_redis_error = str(exc)
            self._redis_limiter = None
            return self._fallback.allow(key=key, limit=limit, window_seconds=window_seconds)
