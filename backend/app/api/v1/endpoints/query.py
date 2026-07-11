"""Grounded question answering over the document library."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentPrincipal, DbSession, Principal
from app.api.v1.endpoints.threads import DEFAULT_TITLE, get_owned_thread
from app.core.exceptions import PermissionDeniedError
from app.schemas.query import (
    BatchQueryRequest,
    BatchQueryResponse,
    QueryCitation,
    QueryRequest,
    QueryResponse,
)
from app.services.access import allowed_document_ids, restrict_requested_ids
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
    thread = None
    if request.thread_id is not None:
        if principal.user_id is None:
            raise PermissionDeniedError("Threads require a user session, not an API key.")
        thread = await get_owned_thread(db, request.thread_id, principal.user_id)

    allowed = await allowed_document_ids(db, principal)
    effective_ids = restrict_requested_ids(allowed, request.document_ids)

    profile = get_profile(request.profile or DEFAULT_PROFILE)
    outcome = await GenerationService(db).answer(
        request.query,
        profile,
        user_id=principal.user_id,
        api_key_id=principal.api_key_id,
        thread_id=thread.id if thread else None,
        document_ids=effective_ids,
        top_k=request.top_k,
    )
    if thread is not None:
        if thread.title == DEFAULT_TITLE:
            thread.title = request.query[:200]
        thread.updated_at = datetime.now(timezone.utc)
        await db.commit()
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


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post(
    "/stream",
    summary="Ask a question; stream the verified answer as server-sent events",
)
async def query_stream(
    payload: QueryRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    background: BackgroundTasks,
) -> StreamingResponse:
    """Streams the VERIFIED answer: the full pipeline (retrieval, generation,
    groundedness, confidence) completes before the first token is sent, so
    nothing unverified ever renders. Events: meta -> token* -> result."""
    response = await _answer_one(payload, db, principal, background)

    async def events() -> AsyncIterator[str]:
        yield _sse("meta", {"query_id": str(response.query_id), "profile": response.profile})
        if response.answered and response.answer:
            words = response.answer.split(" ")
            for i in range(0, len(words), 3):
                yield _sse("token", {"text": " ".join(words[i : i + 3]) + " "})
                await asyncio.sleep(0.012)
        yield _sse("result", json.loads(response.model_dump_json()))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
