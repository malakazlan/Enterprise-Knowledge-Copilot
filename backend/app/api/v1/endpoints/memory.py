"""Agent memory endpoints — private, scoped, semantic.

Any authenticated principal (user session or API key, any role) owns exactly
one memory scope and can only touch that scope. Admins may address another
scope explicitly (operational escape hatch).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentPrincipal, DbSession, limit_query_rate
from app.core.exceptions import PermissionDeniedError
from app.models.user import UserRole
from app.services.memory import MemoryService, principal_scope

router = APIRouter(tags=["memory"], dependencies=[Depends(limit_query_rate)])


class MemoryCreate(BaseModel):
    content: str = Field(min_length=3, max_length=10_000)
    kind: Literal["fact", "episode", "preference"] = "fact"
    source: str | None = Field(default=None, max_length=200)
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
    # Admin-only: write into another scope.
    scope: str | None = Field(default=None, max_length=200)


class MemoryRecallRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=25)
    scope: str | None = Field(default=None, max_length=200)


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: str
    kind: str
    content: str
    source: str | None
    expires_at: datetime | None
    created_at: datetime


class MemoryMatch(MemoryRead):
    score: float


def _resolve_scope(principal: CurrentPrincipal, requested: str | None) -> str:
    own = principal_scope(principal)
    if requested is None or requested == own:
        return own
    if principal.role != UserRole.ADMIN:
        raise PermissionDeniedError("Only admins may address another memory scope.")
    return requested


@router.post("", response_model=MemoryRead, status_code=201, summary="Remember something")
async def remember(payload: MemoryCreate, db: DbSession, principal: CurrentPrincipal) -> MemoryRead:
    scope = _resolve_scope(principal, payload.scope)
    memory = await MemoryService(db).remember(
        scope=scope,
        content=payload.content,
        kind=payload.kind,
        source=payload.source,
        ttl_days=payload.ttl_days,
    )
    return MemoryRead.model_validate(memory)


@router.post("/recall", response_model=list[MemoryMatch], summary="Semantic recall in my scope")
async def recall(
    payload: MemoryRecallRequest, db: DbSession, principal: CurrentPrincipal
) -> list[MemoryMatch]:
    scope = _resolve_scope(principal, payload.scope)
    matches = await MemoryService(db).recall(scope=scope, query=payload.query, limit=payload.limit)
    return [
        MemoryMatch(
            id=memory.id,
            scope=memory.scope,
            kind=memory.kind,
            content=memory.content,
            source=memory.source,
            expires_at=memory.expires_at,
            created_at=memory.created_at,
            score=round(score, 4),
        )
        for memory, score in matches
    ]


@router.get("", response_model=list[MemoryRead], summary="List my memories (newest first)")
async def list_memories(
    db: DbSession,
    principal: CurrentPrincipal,
    limit: int = Query(default=50, ge=1, le=200),
    scope: str | None = Query(default=None),
) -> list[MemoryRead]:
    resolved = _resolve_scope(principal, scope)
    memories = await MemoryService(db).list_memories(scope=resolved, limit=limit)
    return [MemoryRead.model_validate(memory) for memory in memories]


@router.delete("/{memory_id}", status_code=204, summary="Forget one memory")
async def forget(db: DbSession, principal: CurrentPrincipal, memory_id: uuid.UUID) -> None:
    await MemoryService(db).forget(scope=principal_scope(principal), memory_id=memory_id)
