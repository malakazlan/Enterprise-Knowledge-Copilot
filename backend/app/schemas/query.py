"""Grounded query request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    profile: str | None = None
    # Restrict answering to specific documents.
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    # Overrides the profile's final_top_n evidence count when provided.
    top_k: int | None = Field(default=None, ge=1, le=50)


class QueryCitation(BaseModel):
    marker: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    title: str | None
    page_number: int | None
    snippet: str


class QueryResponse(BaseModel):
    query_id: uuid.UUID
    query: str
    profile: str
    answer: str | None
    answered: bool
    # Stable machine-readable slug when refused: no_relevant_documents |
    # insufficient_evidence | missing_citations | low_confidence
    refusal_reason: str | None
    citations: list[QueryCitation]
    confidence: float
    confidence_breakdown: dict[str, float]
    grounded_ratio: float
    needs_review: bool
    model: str
    sources_considered: int
    retrieval_took_ms: float
    took_ms: float
