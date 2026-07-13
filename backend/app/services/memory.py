"""Agent memory service: scoped writes, semantic recall, TTL expiry.

Memories embed on write into the shared vector store under a dedicated
namespace (metadata ``memory_scope``), so recall is dense semantic search
constrained to the caller's scope. Expired memories are purged lazily on the
next write to the same scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.core.exceptions import NotFoundError
from app.models.memory import AgentMemory
from app.services.ingestion.factory import get_embedder, get_vector_store
from app.services.vectorstore import VectorRecord


def principal_scope(principal: Principal) -> str:
    """The private memory namespace this caller owns."""
    if principal.api_key is not None:
        return f"key:{principal.api_key.name}"
    if principal.user is not None:
        return f"user:{principal.user.email}"
    return "anonymous"  # pragma: no cover - principals always carry an identity


def _not_expired_clause() -> Any:
    return or_(
        AgentMemory.expires_at.is_(None),
        AgentMemory.expires_at > datetime.now(timezone.utc),
    )


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def remember(
        self,
        *,
        scope: str,
        content: str,
        kind: str = "fact",
        source: str | None = None,
        ttl_days: int | None = None,
    ) -> AgentMemory:
        await self._purge_expired(scope)
        memory = AgentMemory(
            id=uuid.uuid4(),
            scope=scope,
            kind=kind,
            content=content,
            source=source,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(days=ttl_days) if ttl_days else None
            ),
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)

        (vector,) = await get_embedder().embed([content])
        await get_vector_store().upsert(
            [
                VectorRecord(
                    id=str(memory.id),
                    values=vector,
                    metadata={"memory_scope": scope, "kind": kind},
                )
            ]
        )
        return memory

    async def recall(
        self, *, scope: str, query: str, limit: int = 5
    ) -> list[tuple[AgentMemory, float]]:
        embedder = get_embedder()
        embed_query = getattr(embedder, "embed_query", None)
        vector = (
            await embed_query(query)
            if embed_query is not None
            else (await embedder.embed([query]))[0]
        )
        matches = await get_vector_store().query(
            vector, top_k=max(limit * 3, limit), filters={"memory_scope": scope}
        )
        if not matches:
            return []

        scores = {match.id: match.score for match in matches}
        ids = [uuid.UUID(match.id) for match in matches]
        result = await self.db.execute(
            select(AgentMemory).where(
                AgentMemory.id.in_(ids),
                AgentMemory.scope == scope,
                _not_expired_clause(),
            )
        )
        rows = result.scalars().all()
        ranked = sorted(rows, key=lambda row: -scores.get(str(row.id), 0.0))
        return [(row, scores.get(str(row.id), 0.0)) for row in ranked[:limit]]

    async def list_memories(self, *, scope: str, limit: int = 50) -> list[AgentMemory]:
        result = await self.db.execute(
            select(AgentMemory)
            .where(AgentMemory.scope == scope, _not_expired_clause())
            .order_by(desc(AgentMemory.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def forget(self, *, scope: str, memory_id: uuid.UUID) -> None:
        memory = await self.db.get(AgentMemory, memory_id)
        if memory is None or memory.scope != scope:
            raise NotFoundError("Memory not found.")
        await self.db.delete(memory)
        await self.db.commit()
        await get_vector_store().delete([str(memory_id)])

    async def _purge_expired(self, scope: str) -> None:
        result = await self.db.execute(
            select(AgentMemory.id).where(
                AgentMemory.scope == scope,
                AgentMemory.expires_at.is_not(None),
                AgentMemory.expires_at <= datetime.now(timezone.utc),
            )
        )
        expired = [str(row) for (row,) in result.all()]
        if not expired:
            return
        await self.db.execute(
            sql_delete(AgentMemory).where(AgentMemory.id.in_([uuid.UUID(e) for e in expired]))
        )
        await self.db.commit()
        await get_vector_store().delete(expired)
