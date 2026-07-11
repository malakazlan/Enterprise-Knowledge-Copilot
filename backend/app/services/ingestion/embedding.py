"""Embedders.

- ``HashingEmbedder`` — deterministic, dependency-free feature hashing. No
  semantic understanding, but keeps the pipeline fully runnable offline.
- ``OpenAIEmbedder`` — ``text-embedding-3-*`` models via the official SDK
  (verified against 2.45). The output dimension is pinned to the configured
  ``embedding_dimension`` via the API's ``dimensions`` parameter so vectors
  always match the vector-store collection.

Local semantic embedders (sentence-transformers/BGE) implement the same port
as an optional heavy extra.
"""

from __future__ import annotations

import hashlib
import math

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
