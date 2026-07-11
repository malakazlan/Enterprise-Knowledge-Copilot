"""Embedders.

- ``HashingEmbedder`` — deterministic, dependency-free feature hashing. No
  semantic understanding, but keeps the pipeline fully runnable offline.
- ``OpenAIEmbedder`` — ``text-embedding-3-*`` models via the official SDK
  (verified against 2.45). The output dimension is pinned to the configured
  ``embedding_dimension`` via the API's ``dimensions`` parameter so vectors
  always match the vector-store collection.
- ``FastEmbedEmbedder`` — local neural embeddings (BGE et al.) on CPU via
  ONNX (fastembed, verified against 0.8). Real semantic search with zero
  external calls after the one-time model download; ``[local]`` extra.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from typing import Any

import httpx
import openai

from app.core.exceptions import ServiceUnavailableError


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive.")
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            bucket = value % self.dimension
            sign = 1.0 if (value >> 32) & 1 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]


class OpenAIEmbedder:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, http_client=http_client
        )
        self.model = model
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimension,
            )
        except openai.OpenAIError as exc:
            raise ServiceUnavailableError(f"Embedding provider error: {exc}") from exc

        # The API documents index-aligned results; sort defensively anyway.
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]


class FastEmbedEmbedder:
    """Local ONNX embeddings; inference runs in a worker thread (CPU-bound)."""

    name = "fastembed"

    def __init__(self, *, model: str, cache_dir: str | None = None) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - exercised via factory error
            raise ServiceUnavailableError(
                "fastembed is not installed; add the [local] extra to use "
                "EMBEDDER_PROVIDER=fastembed."
            ) from exc

        supported: dict[str, Any] = {
            entry["model"]: entry for entry in TextEmbedding.list_supported_models()
        }
        if model not in supported:
            raise ServiceUnavailableError(f"fastembed does not support model '{model}'.")

        self.model_name = model
        self.dimension = int(supported[model]["dim"])
        self._model = TextEmbedding(model, cache_dir=cache_dir)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(
            lambda: [vector.tolist() for vector in self._model.embed(texts)]
        )

    async def embed_query(self, query: str) -> list[float]:
        """Query-side embedding (adds the model's query instruction, e.g. BGE)."""
        return await asyncio.to_thread(
            lambda: next(iter(self._model.query_embed([query]))).tolist()
        )
