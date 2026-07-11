"""Value objects shared across the retrieval engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RetrievedChunk:
    """A hydrated retrieval candidate with full score provenance."""

    chunk_id: str
    document_id: str
    filename: str
    title: str | None
    page_number: int | None
    chunk_index: int
    content: str
    fused_score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None
    channels: list[str] = field(default_factory=list)
