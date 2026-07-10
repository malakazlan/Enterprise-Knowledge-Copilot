"""Embedders.

``HashingEmbedder`` is a deterministic, dependency-free feature-hashing
embedder: it hashes tokens into a fixed-width vector, so documents that share
vocabulary land near each other. It has no semantic understanding, but it makes
the pipeline fully runnable and testable offline. Real embedders (OpenAI,
Cohere, local sentence-transformers) implement the same port.
"""

from __future__ import annotations

import hashlib
import math


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
