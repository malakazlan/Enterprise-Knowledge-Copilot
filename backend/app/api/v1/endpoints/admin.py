"""Deployment statistics for the admin dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy import Select, func, select

from app.api.deps import DbSession, require_principal_roles
from app.core.exceptions import NotFoundError
from app.models.apikey import ApiKey
from app.models.document import Document, DocumentChunk, IngestionStatus
from app.models.querylog import QueryLog, ReviewStatus
from app.models.user import User, UserRole
from app.models.webhook import Webhook
from app.schemas.review import AdminStats
from app.schemas.webhook import WebhookCreate, WebhookRead

router = APIRouter(tags=["admin"], dependencies=[Depends(require_principal_roles(UserRole.ADMIN))])


@router.get("/stats", response_model=AdminStats, summary="Deployment statistics")
async def stats(db: DbSession) -> AdminStats:
    async def count(query: Select[Any]) -> int:
        return int((await db.execute(query)).scalar_one() or 0)

    refusals = await db.execute(
        select(QueryLog.refusal_reason, func.count(QueryLog.id))
        .where(QueryLog.refusal_reason.is_not(None))
        .group_by(QueryLog.refusal_reason)
    )
    avg_confidence = (
        await db.execute(select(func.avg(QueryLog.confidence)).where(QueryLog.answered.is_(True)))
    ).scalar_one()

    return AdminStats(
        documents_total=await count(select(func.count(Document.id))),
        documents_failed=await count(
            select(func.count(Document.id)).where(Document.status == IngestionStatus.FAILED)
        ),
        documents_stale=await count(
            select(func.count(Document.id)).where(Document.verify_by < datetime.now(timezone.utc))
        ),
        chunks_total=await count(select(func.count(DocumentChunk.id))),
        queries_total=await count(select(func.count(QueryLog.id))),
        queries_answered=await count(
            select(func.count(QueryLog.id)).where(QueryLog.answered.is_(True))
        ),
        queries_refused=await count(
            select(func.count(QueryLog.id)).where(QueryLog.answered.is_(False))
        ),
        refusal_breakdown={reason: int(n) for reason, n in refusals.all()},
        avg_confidence_answered=round(float(avg_confidence), 4) if avg_confidence else None,
        reviews_pending=await count(
            select(func.count(QueryLog.id)).where(QueryLog.review_status == ReviewStatus.PENDING)
        ),
        api_keys_active=await count(
            select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))
        ),
        users_total=await count(select(func.count(User.id))),
    )


def _webhook_read(hook: Webhook) -> WebhookRead:
    read = WebhookRead.model_validate(hook)
    read.has_secret = hook.secret is not None
    return read


@router.post(
    "/webhooks",
    response_model=WebhookRead,
    status_code=http_status.HTTP_201_CREATED,
    summary="Register an outbound webhook",
)
async def create_webhook(payload: WebhookCreate, db: DbSession) -> WebhookRead:
    hook = Webhook(
        id=uuid.uuid4(),
        url=str(payload.url),
        secret=payload.secret,
        events=payload.events,
        is_active=True,
    )
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    return _webhook_read(hook)


@router.get("/webhooks", response_model=list[WebhookRead], summary="List webhooks")
async def list_webhooks(db: DbSession) -> list[WebhookRead]:
    result = await db.execute(select(Webhook).order_by(Webhook.created_at))
    return [_webhook_read(hook) for hook in result.scalars().all()]


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook",
)
async def delete_webhook(db: DbSession, webhook_id: uuid.UUID) -> None:
    hook = await db.get(Webhook, webhook_id)
    if hook is None:
        raise NotFoundError("Webhook not found.")
    await db.delete(hook)
    await db.commit()
