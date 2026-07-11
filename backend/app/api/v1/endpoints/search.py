"""Hybrid search over the indexed document library."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.profiles.loader import DEFAULT_PROFILE, get_profile
from app.services.retrieval.service import RetrievalService

router = APIRouter(tags=["search"])


@router.post("", response_model=SearchResponse, summary="Hybrid search (dense + BM25 + rerank)")
async def search(
    payload: SearchRequest, db: DbSession, _current_user: CurrentUser
) -> SearchResponse:
    profile = get_profile(payload.profile or DEFAULT_PROFILE)
    outcome = await RetrievalService(db).search(
        payload.query,
        profile,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )
    return SearchResponse(
        query=payload.query,
        profile=profile.name,
        results=[
            SearchResultItem(
                chunk_id=uuid.UUID(chunk.chunk_id),
                document_id=uuid.UUID(chunk.document_id),
                filename=chunk.filename,
                title=chunk.title,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=(
                    chunk.rerank_score
                    if outcome.reranked and chunk.rerank_score is not None
                    else chunk.fused_score
                ),
                fused_score=chunk.fused_score,
                dense_score=chunk.dense_score,
                sparse_score=chunk.sparse_score,
                rerank_score=chunk.rerank_score,
                channels=chunk.channels,
            )
            for chunk in outcome.results
        ],
        dense_candidates=outcome.dense_candidates,
        sparse_candidates=outcome.sparse_candidates,
        reranked=outcome.reranked,
        took_ms=outcome.took_ms,
    )
