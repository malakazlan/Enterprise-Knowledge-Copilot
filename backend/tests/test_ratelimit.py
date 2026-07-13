"""Tests for rate limiting: auth brute-force guard and per-principal query caps."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.core import ratelimit
from app.core.config import settings
from app.models.user import User, UserRole

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]

LOGIN = "/api/v1/auth/login"


@pytest.fixture
async def tight_limits() -> AsyncIterator[None]:
    """Enable rate limiting with tiny windows for the duration of a test."""
    ratelimit.reset_limiters()
    settings.rate_limit_enabled = True
    settings.rate_limit_auth_per_minute = 3
    settings.rate_limit_query_per_minute = 2
    yield
    settings.rate_limit_enabled = False
    ratelimit.reset_limiters()


async def test_login_attempts_are_limited_per_ip(client: AsyncClient, tight_limits: None) -> None:
    bad = {"email": "nobody@example.com", "password": "wrong-password-1"}
    statuses = [(await client.post(LOGIN, json=bad)).status_code for _ in range(4)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429

    limited = await client.post(LOGIN, json=bad)
    body = limited.json()
    assert body["error"]["code"] == "rate_limited"
    assert "Retry" in body["error"]["message"]


async def test_query_limited_per_principal_not_globally(
    client: AsyncClient,
    make_user: MakeUser,
    auth_headers: AuthHeaders,
    tight_limits: None,
) -> None:
    await make_user("a@example.com", role=UserRole.ADMIN)
    await make_user("b@example.com", role=UserRole.ADMIN)
    first = await auth_headers("a@example.com")
    second = await auth_headers("b@example.com")

    payload = {"query": "anything at all"}
    first_resp = await client.post("/api/v1/query", headers=first, json=payload)
    assert first_resp.status_code == 200, first_resp.text
    assert (await client.post("/api/v1/query", headers=first, json=payload)).status_code == 200
    assert (await client.post("/api/v1/query", headers=first, json=payload)).status_code == 429

    # A different principal has its own window.
    assert (await client.post("/api/v1/query", headers=second, json=payload)).status_code == 200

    # Search shares the query scope.
    assert (await client.post("/api/v1/search", headers=second, json=payload)).status_code == 200
    assert (await client.post("/api/v1/search", headers=second, json=payload)).status_code == 429


async def test_window_slides() -> None:
    limiter = ratelimit.SlidingWindowLimiter(limit=2, window_seconds=0.05)
    await limiter.check("k")
    await limiter.check("k")
    with pytest.raises(Exception, match="Retry"):
        await limiter.check("k")
    import asyncio

    await asyncio.sleep(0.06)
    await limiter.check("k")  # window slid; allowed again


async def test_redis_backend_shares_windows() -> None:
    """Runs against the stack's real Redis; skipped when it isn't up."""
    import redis.asyncio as aioredis

    try:
        probe = aioredis.from_url(settings.redis_url)
        await probe.ping()
    except Exception:
        pytest.skip("Redis not reachable")
    finally:
        try:
            await probe.aclose()
        except Exception:
            pass

    key = f"test-{__import__('uuid').uuid4().hex}"
    limiter = ratelimit.RedisSlidingWindowLimiter(limit=2, scope="pytest", window_seconds=1.0)
    await limiter.check(key)
    await limiter.check(key)
    with pytest.raises(Exception, match="Retry"):
        await limiter.check(key)
    # Other keys are unaffected; a second limiter instance (another "replica")
    # sees the same shared window.
    await limiter.check(f"{key}-other")
    other_replica = ratelimit.RedisSlidingWindowLimiter(limit=2, scope="pytest", window_seconds=1.0)
    with pytest.raises(Exception, match="Retry"):
        await other_replica.check(key)
    ratelimit.reset_limiters()
