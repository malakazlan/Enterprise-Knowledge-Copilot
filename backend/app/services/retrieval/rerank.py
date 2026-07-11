"""Reranker port and adapters.

- ``LexicalBM25Reranker`` — re-scores the fused pool with BM25 computed
  *locally over the pool* (candidate-set statistics, not corpus statistics).
  Cheap, deterministic, dependency-free baseline.
- ``OnnxCrossEncoderReranker`` — a real cross-encoder (query and passage
  scored together) on CPU via ONNX (fastembed, verified against 0.8). This is
  where answer quality is won; ``[local]`` extra.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from app.core.exceptions import ServiceUnavailableError
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


class OnnxCrossEncoderReranker:
    """Cross-encoder reranking; inference runs in a worker thread (CPU-bound)."""

    name = "onnx-cross-encoder"

    def __init__(self, *, model: str, cache_dir: str | None = None) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:  # pragma: no cover - exercised via factory error
            raise ServiceUnavailableError(
                "fastembed is not installed; add the [local] extra to use RERANKER_PROVIDER=onnx."
            ) from exc

        self.model_name = model
        self._encoder = TextCrossEncoder(model, cache_dir=cache_dir)

    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], *, top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        scores = await asyncio.to_thread(
            lambda: list(self._encoder.rerank(query, [chunk.content for chunk in candidates]))
        )
        for chunk, score in zip(candidates, scores, strict=True):
            chunk.rerank_score = float(score)

        reordered = sorted(candidates, key=lambda chunk: -(chunk.rerank_score or 0.0))
        return reordered[:top_n]
