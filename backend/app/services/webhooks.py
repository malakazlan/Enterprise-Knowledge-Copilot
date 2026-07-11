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


async def deliver(event: str, targets: list[Target], payload: dict[str, Any]) -> None:
    """POST the event to each target (DB-free; safe as a background task)."""
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
            try:
                response = await client.post(url, content=body, headers=headers)
                logger.info(
                    "webhook_delivered", hook_event=event, url=url, status_code=response.status_code
                )
            except httpx.HTTPError as exc:
                logger.warning("webhook_failed", hook_event=event, url=url, error=str(exc))
