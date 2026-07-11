"""Hybrid retrieval: dense + sparse -> RRF fusion -> hydration -> rerank.

All tuning comes from the active :class:`RagProfile`; nothing is hardcoded.
Both channels emit chunk IDs, which are hydrated from the database (the source
of truth) — a candidate whose chunk has been deleted silently drops out.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.ingestion.factory import get_embedder, get_vector_store
from app.services.ingestion.ports import Embedder
from app.services.profiles.schema import RagProfile
from app.services.retrieval.factory import get_reranker, get_sparse_index
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.sparse import LocalBM25Index
from app.services.retrieval.types import RetrievedChunk
from app.services.vectorstore import VectorStore

logger = structlog.get_logger("app.retrieval")


@dataclass(slots=True)
class SearchOutcome:
    results: list[RetrievedChunk]
    dense_candidates: int
    sparse_candidates: int
    reranked: bool
    took_ms: float


class RetrievalService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        sparse_index: LocalBM25Index | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder or get_embedder()
        self.vector_store = vector_store or get_vector_store()
        self.sparse_index = sparse_index or get_sparse_index()
        self.reranker = get_reranker()

    async def search(
        self,
        query: str,
        profile: RagProfile,
        *,
        top_k: int | None = None,
        document_ids: list[uuid.UUID] | None = None,
    ) -> SearchOutcome:
        started = time.perf_counter()
        config = profile.retrieval
        final_n = top_k or config.final_top_n
        id_filter = [str(document_id) for document_id in document_ids] if document_ids else None

        # --- Dense channel ---
        query_vector = (await self.embedder.embed([query]))[0]
        dense_matches = await self.vector_store.query(
            query_vector,
            top_k=config.dense_top_k,
            filters={"document_id": id_filter} if id_filter else None,
        )
        if config.min_dense_score is not None:
            dense_matches = [
                match for match in dense_matches if match.score >= config.min_dense_score
            ]

        # --- Sparse channel ---
        await self.sparse_index.ensure_fresh(self.db)
        sparse_matches = self.sparse_index.search(
            query,
            top_k=config.sparse_top_k,
            document_ids=set(id_filter) if id_filter else None,
        )

        # --- Fusion ---
        dense_ranking = [match.id for match in dense_matches]
        sparse_ranking = [chunk_id for chunk_id, _ in sparse_matches]
        fused = reciprocal_rank_fusion([dense_ranking, sparse_ranking], k=config.rrf_k)
        ordered_ids = sorted(fused, key=lambda chunk_id: -fused[chunk_id])

        # --- Hydration from the database (source of truth) ---
        dense_scores = {match.id: match.score for match in dense_matches}
        sparse_scores = dict(sparse_matches)
        candidates = await self._hydrate(ordered_ids, fused, dense_scores, sparse_scores)

        # --- Rerank ---
        reranked = False
        if config.rerank_enabled and self.reranker is not None:
            candidates = await self.reranker.rerank(query, candidates, top_n=final_n)
            reranked = True
        else:
            candidates = candidates[:final_n]

        took_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "search_completed",
            profile=profile.name,
            dense=len(dense_ranking),
            sparse=len(sparse_ranking),
            returned=len(candidates),
            reranked=reranked,
            took_ms=took_ms,
        )
        return SearchOutcome(
            results=candidates,
            dense_candidates=len(dense_ranking),
            sparse_candidates=len(sparse_ranking),
            reranked=reranked,
            took_ms=took_ms,
        )

    async def _hydrate(
        self,
        ordered_ids: list[str],
        fused: dict[str, float],
        dense_scores: dict[str, float],
        sparse_scores: dict[str, float],
    ) -> list[RetrievedChunk]:
        if not ordered_ids:
            return []

        chunk_uuids = [uuid.UUID(chunk_id) for chunk_id in ordered_ids]
        rows = await self.db.execute(
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.id.in_(chunk_uuids))
        )
        by_id = {str(chunk.id): (chunk, document) for chunk, document in rows.all()}

        candidates: list[RetrievedChunk] = []
        for chunk_id in ordered_ids:
            entry = by_id.get(chunk_id)
            if entry is None:  # stale vector/sparse hit; chunk no longer exists
                continue
            chunk, document = entry
            channels = []
            if chunk_id in dense_scores:
                channels.append("dense")
            if chunk_id in sparse_scores:
                channels.append("sparse")
            candidates.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=str(document.id),
                    filename=document.filename,
                    title=document.title,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    fused_score=fused[chunk_id],
                    dense_score=dense_scores.get(chunk_id),
                    sparse_score=sparse_scores.get(chunk_id),
                    channels=channels,
                )
            )
        return candidates
