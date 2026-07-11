"""Request rate limiting.

In-process sliding windows keyed by caller identity: authenticated requests
are limited per user / API key; anonymous auth attempts per client IP (the
brute-force guard). Limits are per replica — a distributed (Redis) limiter
implements the same interface when horizontal scale demands it.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitError


@dataclass
class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window_seconds` per key."""

    limit: int
    window_seconds: float = 60.0
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, key: str) -> None:
        """Record a hit; raise RateLimitError when the window is full."""
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            retry_after = int(window[0] + self.window_seconds - now) + 1
            raise RateLimitError(f"Too many requests. Retry in about {retry_after} seconds.")
        window.append(now)


# Process-wide limiters, sized lazily from settings on first use.
_limiters: dict[str, SlidingWindowLimiter] = {}


def _limiter(scope: str, limit: int) -> SlidingWindowLimiter:
    existing = _limiters.get(scope)
    if existing is None or existing.limit != limit:
        existing = SlidingWindowLimiter(limit=limit)
        _limiters[scope] = existing
    return existing


def client_ip(request: Request) -> str:
    """Client address, honouring the first hop of X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_auth(request: Request) -> None:
    """Per-IP limit for credential endpoints (login/register)."""
    if not settings.rate_limit_enabled:
        return
    _limiter("auth", settings.rate_limit_auth_per_minute).check(client_ip(request))


def query_rate_key(request: Request, principal: object) -> str:
    """Stable identity key for the query/search scope."""
    user = getattr(principal, "user", None)
    if user is not None:
        return f"user:{user.id}"
    api_key = getattr(principal, "api_key", None)
    if api_key is not None:
        return f"key:{api_key.id}"
    return f"ip:{client_ip(request)}"


def check_query_rate(key: str) -> None:
    _limiter("query", settings.rate_limit_query_per_minute).check(key)


def reset_limiters() -> None:
    """Test hook: forget all windows."""
    _limiters.clear()
