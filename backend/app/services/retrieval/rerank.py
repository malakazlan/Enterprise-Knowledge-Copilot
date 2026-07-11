"""Reranker port and the built-in lexical adapter.

``LexicalBM25Reranker`` re-scores the fused candidate pool with BM25 computed
*locally over the pool* (candidate-set statistics, not corpus statistics), so
IDF reflects what actually discriminates among the candidates. It is a cheap,
deterministic, dependency-free baseline; cross-encoder adapters (bge-reranker,
Cohere) implement the same port and simply replace it via configuration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.retrieval.bm25 import BM25Index
from app.services.retrieval.tokenize import tokenize
from app.services.retrieval.types import RetrievedChunk


@runtime_checkable
class Reranker(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], *, top_n: int
    ) -> list[RetrievedChunk]:
        """Return the top ``top_n`` candidates, best first, with rerank scores set."""
        ...


class LexicalBM25Reranker:
    name = "lexical-bm25"

    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], *, top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        index = BM25Index()
        index.build([(chunk.chunk_id, tokenize(chunk.content)) for chunk in candidates])
        scores = dict(index.search(tokenize(query), top_k=len(candidates)))

        for chunk in candidates:
            chunk.rerank_score = scores.get(chunk.chunk_id, 0.0)

        # Stable sort: candidates the reranker cannot separate keep fused order.
        reordered = sorted(candidates, key=lambda chunk: -(chunk.rerank_score or 0.0))
        return reordered[:top_n]
