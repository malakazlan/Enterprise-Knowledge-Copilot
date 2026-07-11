"""Provider factories for the retrieval engine."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services.retrieval.rerank import LexicalBM25Reranker, Reranker
from app.services.retrieval.sparse import LocalBM25Index


@lru_cache
def get_sparse_index() -> LocalBM25Index:
    provider = settings.sparse_provider
    if provider == "local-bm25":
        return LocalBM25Index()
    raise ServiceUnavailableError(f"Sparse provider '{provider}' is not configured.")


@lru_cache
def get_reranker() -> Reranker | None:
    provider = settings.reranker_provider
    if provider == "lexical":
        return LexicalBM25Reranker()
    if provider == "none":
        return None
    if provider == "onnx":
        from app.services.retrieval.rerank import OnnxCrossEncoderReranker

        return OnnxCrossEncoderReranker(
            model=settings.reranker_model, cache_dir=settings.model_cache_dir
        )
    raise ServiceUnavailableError(f"Reranker provider '{provider}' is not configured.")
