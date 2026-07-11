"""Webhook delivery: signed, best-effort pushes of trust events.

Deliveries are HMAC-SHA256 signed when the webhook has a secret, so receivers
can verify authenticity:

    signature = HMAC_SHA256(secret, raw_request_body)
    header    = X-EKC-Signature: sha256=<hex digest>

Subscriptions are loaded during the request (the DB session is request-scoped
and unavailable to background tasks); delivery itself is DB-free and runs
after the response. One attempt, short timeout: webhooks are notifications,
not the system of record — the query log remains authoritative.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.webhook import Webhook

logger = get_logger("app.webhooks")

_DELIVERY_TIMEOUT = 10.0

# (url, secret) pairs resolved during the request.
Target = tuple[str, str | None]

# Test seam: routes deliveries into a mock transport.
_transport: httpx.AsyncBaseTransport | None = None


async def subscribed(db: AsyncSession, event: str) -> list[Target]:
    """Active webhooks subscribed to `event`."""
    result = await db.execute(select(Webhook).where(Webhook.is_active.is_(True)))
    return [(h.url, h.secret) for h in result.scalars().all() if event in (h.events or [])]


# Waits before the 2nd and 3rd delivery attempts (tests shrink these).
_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 4.0)


async def deliver(event: str, targets: list[Target], payload: dict[str, Any]) -> None:
    """POST the event to each target (DB-free; safe as a background task).

    Network errors and 5xx responses are retried with backoff — the receiver
    was willing but unable. 4xx responses are NOT retried: the registration
    is misconfigured and repeating the request cannot fix it.
    """
    if not targets:
        return
    body = json.dumps(
        {"event": event, "delivery_id": uuid.uuid4().hex, "data": payload},
        default=str,
    ).encode()

    async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT, transport=_transport) as client:
        for url, secret in targets:
            headers = {"Content-Type": "application/json", "X-EKC-Event": event}
            if secret:
                digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                headers["X-EKC-Signature"] = f"sha256={digest}"
            await _deliver_one(client, url, body, headers, event)


async def _deliver_one(
    client: httpx.AsyncClient, url: str, body: bytes, headers: dict[str, str], event: str
) -> None:
    attempts = len(_RETRY_BACKOFF_SECONDS) + 1
    for attempt in range(1, attempts + 1):
        try:
            response = await client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            failure = str(exc)
        else:
            if response.status_code < 500:
                log = logger.info if response.status_code < 400 else logger.warning
                log(
                    "webhook_delivered",
                    hook_event=event,
                    url=url,
                    status_code=response.status_code,
                    attempt=attempt,
                )
                return
            failure = f"HTTP {response.status_code}"

        if attempt < attempts:
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt - 1])
        else:
            logger.warning(
                "webhook_failed", hook_event=event, url=url, error=failure, attempts=attempts
            )
