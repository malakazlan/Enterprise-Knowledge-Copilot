"""Grounded question answering over the document library."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.schemas.query import QueryCitation, QueryRequest, QueryResponse
from app.services.generation.service import GenerationService
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile

router = APIRouter(tags=["query"])

_SNIPPET_CHARS = 300


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question; get a cited, confidence-scored answer",
)
async def query(payload: QueryRequest, db: DbSession, principal: CurrentPrincipal) -> QueryResponse:
    profile = get_profile(payload.profile or DEFAULT_PROFILE)
    outcome = await GenerationService(db).answer(
        payload.query,
        profile,
        user_id=principal.user_id,
        api_key_id=principal.api_key_id,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
    return QueryResponse(
        query_id=outcome.query_id,
        query=payload.query,
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
