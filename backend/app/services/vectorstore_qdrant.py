"""Qdrant adapter for the :class:`VectorStore` port.

Verified against qdrant-client 1.18 / Qdrant server (query_points API).
Collections are created lazily on first use with cosine distance. Writes use
``wait=True`` for read-after-write consistency — ingestion is a background
concern, so durability beats a few milliseconds of latency.
"""

from __future__ import annotations

import asyncio
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.services.vectorstore import VectorMatch, VectorRecord


def _build_filter(filters: dict[str, Any]) -> models.Filter:
    conditions: list[models.FieldCondition] = []
    for key, expected in filters.items():
        if isinstance(expected, list):
            conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=expected)))
        else:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=expected))
            )
    return models.Filter(must=conditions)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        collection: str,
        dimension: int,
    ) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._collection = collection
        self._dimension = dimension
        self._ready = False
        self._init_lock = asyncio.Lock()

    async def _ensure_collection(self) -> None:
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            if not await self._client.collection_exists(self._collection):
                await self._client.create_collection(
                    self._collection,
                    vectors_config=models.VectorParams(
                        size=self._dimension, distance=models.Distance.COSINE
                    ),
                )
            self._ready = True

    async def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        await self._ensure_collection()
        points = [
            models.PointStruct(
                id=record.id,
                vector=record.values,
                # Drop nulls: absent keys keep payloads lean and filterable.
                payload={k: v for k, v in record.metadata.items() if v is not None},
            )
            for record in records
        ]
        await self._client.upsert(self._collection, points=points, wait=True)

    async def query(
        self, vector: list[float], *, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[VectorMatch]:
        await self._ensure_collection()
        response = await self._client.query_points(
            self._collection,
            query=vector,
            limit=top_k,
            query_filter=_build_filter(filters) if filters else None,
            with_payload=True,
        )
        return [
            VectorMatch(id=str(point.id), score=point.score, metadata=dict(point.payload or {}))
            for point in response.points
        ]

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        await self._ensure_collection()
        await self._client.delete(
            self._collection,
            points_selector=models.PointIdsList(points=list(ids)),
            wait=True,
        )

    async def delete_by_document(self, document_id: str) -> None:
        await self._ensure_collection()
        await self._client.delete(
            self._collection,
            points_selector=models.FilterSelector(
                filter=_build_filter({"document_id": document_id})
            ),
            wait=True,
        )

    async def drop(self) -> None:
        """Delete the whole collection (tests, resets)."""
        if await self._client.collection_exists(self._collection):
            await self._client.delete_collection(self._collection)
        self._ready = False

    async def close(self) -> None:
        await self._client.close()
