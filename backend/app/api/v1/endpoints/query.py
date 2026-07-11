"""Grounded question answering over the document library."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, BackgroundTasks

from app.api.deps import CurrentPrincipal, DbSession, Principal
from app.schemas.query import (
    BatchQueryRequest,
    BatchQueryResponse,
    QueryCitation,
    QueryRequest,
    QueryResponse,
)
from app.services.generation.service import GenerationService
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile
from app.services.webhooks import deliver, subscribed

router = APIRouter(tags=["query"])

_SNIPPET_CHARS = 300


async def _answer_one(
    request: QueryRequest,
    db: DbSession,
    principal: Principal,
    background: BackgroundTasks,
) -> QueryResponse:
    """Answer a single question, firing trust-event webhooks as needed."""
    profile = get_profile(request.profile or DEFAULT_PROFILE)
    outcome = await GenerationService(db).answer(
        request.query,
        profile,
        user_id=principal.user_id,
        api_key_id=principal.api_key_id,
        document_ids=request.document_ids,
        top_k=request.top_k,
    )
    event = (
        "query.refused"
        if not outcome.answered
        else "query.needs_review"
        if outcome.needs_review
        else None
    )
    if event:
        targets = await subscribed(db, event)
        if targets:
            background.add_task(
                deliver,
                event,
                targets,
                {
                    "query_id": str(outcome.query_id),
                    "query": request.query,
                    "profile": profile.name,
                    "confidence": outcome.confidence,
                    "refusal_reason": outcome.refusal_reason,
                    "needs_review": outcome.needs_review,
                },
            )

    return QueryResponse(
        query_id=outcome.query_id,
        query=request.query,
        profile=profile.name,
        answer=outcome.answer,
        answered=outcome.answered,
        refusal_reason=outcome.refusal_reason,
        citations=[
            QueryCitation(
                marker=citation.marker,
                chunk_id=uuid.UUID(citation.chunk.chunk_id),
                document_id=uuid.UUID(citation.chunk.document_id),
                filename=citation.chunk.filename,
                title=citation.chunk.title,
                page_number=citation.chunk.page_number,
                snippet=citation.chunk.content[:_SNIPPET_CHARS],
            )
            for citation in outcome.citations
        ],
        confidence=outcome.confidence,
        confidence_breakdown=outcome.confidence_breakdown,
        grounded_ratio=outcome.grounded_ratio,
        needs_review=outcome.needs_review,
        model=outcome.model,
        sources_considered=outcome.sources_considered,
        retrieval_took_ms=outcome.retrieval_took_ms,
        took_ms=outcome.took_ms,
    )


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question; get a cited, confidence-scored answer",
)
async def query(
    payload: QueryRequest, db: DbSession, principal: CurrentPrincipal, background: BackgroundTasks
) -> QueryResponse:
    return await _answer_one(payload, db, principal, background)


@router.post(
    "/batch",
    response_model=BatchQueryResponse,
    summary="Answer up to 25 questions in one call (automation workloads)",
)
async def query_batch(
    payload: BatchQueryRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
) -> BatchQueryResponse:
    """Questions run sequentially against one session; each is logged and
    fires webhooks exactly like a single query."""
    start = time.perf_counter()
    results = [
        await _answer_one(
            QueryRequest(query=question, profile=payload.profile, top_k=payload.top_k),
            db,
            principal,
            background,
        )
        for question in payload.queries
    ]
    answered = sum(1 for r in results if r.answered)
    return BatchQueryResponse(
        results=results,
        total=len(results),
        answered=answered,
        refused=len(results) - answered,
        took_ms=round((time.perf_counter() - start) * 1000, 2),
    )
