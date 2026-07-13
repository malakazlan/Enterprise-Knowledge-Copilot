"""Request rate limiting.

Sliding windows keyed by caller identity: authenticated requests are limited
per user / API key; anonymous auth attempts per client IP (the brute-force
guard). Two backends behind one interface:

- ``memory`` (default) — per-replica, zero dependencies.
- ``redis``            — shared across replicas (RATE_LIMIT_BACKEND=redis;
                         uses REDIS_URL), a ZSET per key holding hit
                         timestamps trimmed to the window.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitError


class RateLimiter(Protocol):
    limit: int

    async def check(self, key: str) -> None:
        """Record a hit; raise RateLimitError when the window is full."""
        ...


@dataclass
class SlidingWindowLimiter:
    """In-process window: allows `limit` hits per `window_seconds` per key."""

    limit: int
    window_seconds: float = 60.0
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    async def check(self, key: str) -> None:
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            retry_after = int(window[0] + self.window_seconds - now) + 1
            raise RateLimitError(f"Too many requests. Retry in about {retry_after} seconds.")
        window.append(now)


@dataclass
class RedisSlidingWindowLimiter:
    """Redis-shared window: correct limits across any number of replicas."""

    limit: int
    scope: str
    window_seconds: float = 60.0

    async def check(self, key: str) -> None:
        import redis.asyncio as aioredis

        global _redis_client
        if _redis_client is None:
            _redis_client = aioredis.from_url(settings.redis_url)
        redis_key = f"ratelimit:{self.scope}:{key}"
        now = time.time()
        cutoff = now - self.window_seconds

        async with _redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, "-inf", cutoff)
            pipe.zcard(redis_key)
            _, current = await pipe.execute()

        if int(current) >= self.limit:
            oldest = await _redis_client.zrange(redis_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + self.window_seconds - now) + 1 if oldest else 1
            raise RateLimitError(f"Too many requests. Retry in about {retry_after} seconds.")

        async with _redis_client.pipeline(transaction=True) as pipe:
            pipe.zadd(redis_key, {uuid.uuid4().hex: now})
            pipe.expire(redis_key, int(self.window_seconds) + 1)
            await pipe.execute()


# Process-wide state, sized lazily from settings on first use.
_limiters: dict[str, RateLimiter] = {}
_redis_client = None  # shared connection pool for the redis backend


def _limiter(scope: str, limit: int) -> RateLimiter:
    existing = _limiters.get(scope)
    if existing is None or existing.limit != limit:
        if settings.rate_limit_backend == "redis":
            existing = RedisSlidingWindowLimiter(limit=limit, scope=scope)
        else:
            existing = SlidingWindowLimiter(limit=limit)
        _limiters[scope] = existing
    return existing


def client_ip(request: Request) -> str:
    """Client address, honouring the first hop of X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def limit_auth(request: Request) -> None:
    """Per-IP limit for credential endpoints (login/register)."""
    if not settings.rate_limit_enabled:
        return
    await _limiter("auth", settings.rate_limit_auth_per_minute).check(client_ip(request))


def query_rate_key(request: Request, principal: object) -> str:
    """Stable identity key for the query/search scope."""
    user = getattr(principal, "user", None)
    if user is not None:
        return f"user:{user.id}"
    api_key = getattr(principal, "api_key", None)
    if api_key is not None:
        return f"key:{api_key.id}"
    return f"ip:{client_ip(request)}"


async def check_query_rate(key: str) -> None:
    await _limiter("query", settings.rate_limit_query_per_minute).check(key)


def reset_limiters() -> None:
    """Test hook: forget all windows and the redis connection."""
    global _redis_client
    _limiters.clear()
    _redis_client = None
