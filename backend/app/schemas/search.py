"""Hybrid search request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    # Domain profile to tune retrieval with; defaults to the deployment default.
    profile: str | None = None
    # Overrides the profile's final_top_n when provided.
    top_k: int | None = Field(default=None, ge=1, le=50)
    # Restrict the search to specific documents.
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class SearchResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    title: str | None
    page_number: int | None
    chunk_index: int
    content: str
    # Unified ranking score: rerank score when reranking ran, fused RRF otherwise.
    score: float
    fused_score: float
    dense_score: float | None
    sparse_score: float | None
    rerank_score: float | None
    channels: list[str]


class SearchResponse(BaseModel):
    query: str
    profile: str
    results: list[SearchResultItem]
    dense_candidates: int
    sparse_candidates: int
    reranked: bool
    took_ms: float
