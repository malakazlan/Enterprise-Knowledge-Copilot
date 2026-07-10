"""Vector store abstraction and an in-memory implementation.

The in-memory store gives the ingestion and retrieval pipelines a working
backend with no external dependency. The Pinecone adapter (added later)
implements the same :class:`VectorStore` protocol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class VectorRecord:
    id: str
    values: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord]) -> None: ...
    async def query(
        self, vector: list[float], *, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[VectorMatch]: ...
    async def delete(self, ids: list[str]) -> None: ...
    async def delete_by_document(self, document_id: str) -> None: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Vector dimensions do not match.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in filters.items())


class InMemoryVectorStore:
    """A dict-backed cosine-similarity store."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    async def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record

    async def query(
        self, vector: list[float], *, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[VectorMatch]:
        matches = [
            VectorMatch(record.id, cosine_similarity(vector, record.values), record.metadata)
            for record in self._records.values()
            if filters is None or _matches(record.metadata, filters)
        ]
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    async def delete(self, ids: list[str]) -> None:
        for identifier in ids:
            self._records.pop(identifier, None)

    async def delete_by_document(self, document_id: str) -> None:
        stale = [
            key
            for key, record in self._records.items()
            if record.metadata.get("document_id") == document_id
        ]
        for key in stale:
            self._records.pop(key, None)

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
