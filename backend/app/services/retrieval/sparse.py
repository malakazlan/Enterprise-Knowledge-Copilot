"""Process-local BM25 sparse index, synced lazily from ``document_chunks``.

Freshness: before every search the index compares a cheap corpus version
``(chunk count, max created_at)`` against its cached one and rebuilds on
mismatch. This keeps the API process consistent when ingestion happens in a
separate worker process, at the cost of one aggregate query per search.

Suitable for the default single-node deployment (rebuild is O(corpus)); large
installations swap in a real search backend behind the same contract.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.tokenize import tokenize


class LocalBM25Index:
    def __init__(self) -> None:
        self._index = BM25Index()
        self._chunk_to_document: dict[str, str] = {}
        self._version: tuple[int, str] | None = None

    async def ensure_fresh(self, db: AsyncSession) -> None:
        """Rebuild the index if the chunk corpus changed since the last build."""
        result = await db.execute(
            select(func.count(DocumentChunk.id), func.max(DocumentChunk.created_at))
        )
        count, max_created = result.one()
        version = (int(count or 0), str(max_created))
        if version == self._version:
            return

        rows = await db.execute(
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.content)
        )
        documents: list[tuple[str, list[str]]] = []
        mapping: dict[str, str] = {}
        for chunk_id, document_id, content in rows.all():
            key = str(chunk_id)
            documents.append((key, tokenize(content)))
            mapping[key] = str(document_id)

        self._index.build(documents)
        self._chunk_to_document = mapping
        self._version = version

    def search(
        self, query: str, *, top_k: int, document_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """Return ``(chunk_id, bm25_score)`` pairs, best first."""
        allowed: set[str] | None = None
        if document_ids is not None:
            allowed = {
                chunk_id
                for chunk_id, document_id in self._chunk_to_document.items()
                if document_id in document_ids
            }
        return self._index.search(tokenize(query), top_k=top_k, allowed_ids=allowed)

    def invalidate(self) -> None:
        """Force a rebuild on next use (tests / explicit cache busting)."""
        self._version = None
