"""Behavioral contract every VectorStore implementation must satisfy.

The same assertions run against the in-memory store (always) and against a
real Qdrant server (when ``QDRANT_TEST_URL`` is set — e.g. a local container).
CI without Qdrant skips the integration case; the contract itself still holds.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.services.vectorstore import InMemoryVectorStore, VectorRecord, VectorStore

QDRANT_TEST_URL = os.environ.get("QDRANT_TEST_URL")


def _records() -> list[VectorRecord]:
    return [
        VectorRecord(
            id=str(uuid.uuid4()),
            values=[1.0, 0.0, 0.0, 0.0],
            metadata={"document_id": "doc-a", "chunk_index": 0},
        ),
        VectorRecord(
            id=str(uuid.uuid4()),
            values=[0.9, 0.1, 0.0, 0.0],
            metadata={"document_id": "doc-a", "chunk_index": 1},
        ),
        VectorRecord(
            id=str(uuid.uuid4()),
            values=[0.0, 0.0, 1.0, 0.0],
            metadata={"document_id": "doc-b", "chunk_index": 0},
        ),
    ]


async def _assert_contract(store: VectorStore) -> None:
    records = _records()
    await store.upsert(records)
    probe = [1.0, 0.0, 0.0, 0.0]

    # Ranking: nearest first, scores descending, top_k respected.
    matches = await store.query(probe, top_k=3)
    assert [m.id for m in matches[:2]] == [records[0].id, records[1].id]
    assert matches[0].score >= matches[1].score >= matches[2].score
    assert len(await store.query(probe, top_k=1)) == 1

    # Metadata round-trips.
    assert matches[0].metadata["document_id"] == "doc-a"

    # Equality and membership filters.
    only_b = await store.query(probe, top_k=5, filters={"document_id": "doc-b"})
    assert [m.metadata["document_id"] for m in only_b] == ["doc-b"]
    member = await store.query(probe, top_k=5, filters={"document_id": ["doc-a"]})
    assert {m.metadata["document_id"] for m in member} == {"doc-a"}

    # Upsert is idempotent per id.
    await store.upsert([records[0]])
    assert len(await store.query(probe, top_k=10)) == 3

    # Delete by document, then by id.
    await store.delete_by_document("doc-a")
    remaining = await store.query(probe, top_k=10)
    assert {m.metadata["document_id"] for m in remaining} == {"doc-b"}
    await store.delete([records[2].id])
    assert await store.query(probe, top_k=10) == []


async def test_inmemory_store_contract() -> None:
    await _assert_contract(InMemoryVectorStore())


@pytest.mark.skipif(QDRANT_TEST_URL is None, reason="QDRANT_TEST_URL not set")
async def test_qdrant_store_contract() -> None:
    from app.services.vectorstore_qdrant import QdrantVectorStore

    store = QdrantVectorStore(
        url=QDRANT_TEST_URL or "",
        api_key=None,
        collection=f"contract_{uuid.uuid4().hex[:8]}",
        dimension=4,
    )
    try:
        await _assert_contract(store)
    finally:
        await store.drop()
        await store.close()
