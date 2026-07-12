"""Context packs — token-budgeted context assembly for agent frameworks.

Most agentic workflows don't want a chat answer; they want the best N tokens
of grounded context to inject into their own prompt. This endpoint returns
exactly that: ranked, deduplicated passages with provenance headers, cut to a
token budget, with access control enforced at retrieval time like everywhere
else.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import CurrentPrincipal, DbSession, limit_query_rate
from app.schemas.query import QueryRequest
from app.services.access import allowed_document_ids, restrict_requested_ids
from app.services.ingestion.chunking import estimate_tokens
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile
from app.services.retrieval.service import RetrievalService

router = APIRouter(tags=["context"], dependencies=[Depends(limit_query_rate)])

_MAX_CANDIDATES = 30


class ContextRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    max_tokens: int = Field(default=2000, ge=100, le=16000)
    profile: str | None = None
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class ContextSource(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    page_number: int | None
    score: float


class ContextResponse(BaseModel):
    context: str
    sources: list[ContextSource]
    tokens_used: int
    chunks_included: int
    chunks_considered: int
    took_ms: float


@router.post(
    "",
    response_model=ContextResponse,
    summary="Assemble a token-budgeted context pack for an agent task",
)
async def build_context(
    payload: ContextRequest, db: DbSession, principal: CurrentPrincipal
) -> ContextResponse:
    started = time.perf_counter()
    # Reuse QueryRequest validation semantics for the id filter shape.
    QueryRequest(query=payload.task, document_ids=payload.document_ids)

    allowed = await allowed_document_ids(db, principal)
    effective_ids = restrict_requested_ids(allowed, payload.document_ids)

    profile = get_profile(payload.profile or DEFAULT_PROFILE)
    search = await RetrievalService(db).search(
        payload.task, profile, top_k=_MAX_CANDIDATES, document_ids=effective_ids
    )

    parts: list[str] = []
    sources: list[ContextSource] = []
    budget = payload.max_tokens
    for chunk in search.results:
        page = f", p.{chunk.page_number}" if chunk.page_number is not None else ""
        block = f"[Source: {chunk.filename}{page}]\n{chunk.content}"
        cost = estimate_tokens(block)
        if cost > budget:
            continue
        budget -= cost
        parts.append(block)
        sources.append(
            ContextSource(
                document_id=uuid.UUID(chunk.document_id),
                chunk_id=uuid.UUID(chunk.chunk_id),
                filename=chunk.filename,
                page_number=chunk.page_number,
                score=chunk.rerank_score if chunk.rerank_score is not None else chunk.fused_score,
            )
        )

    context = "\n\n---\n\n".join(parts)
    return ContextResponse(
        context=context,
        sources=sources,
        tokens_used=estimate_tokens(context) if context else 0,
        chunks_included=len(parts),
        chunks_considered=len(search.results),
        took_ms=round((time.perf_counter() - started) * 1000, 2),
    )
