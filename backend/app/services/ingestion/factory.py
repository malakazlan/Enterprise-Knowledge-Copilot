"""Provider factories that resolve ingestion adapters from settings.

Each factory is memoised so implementations that hold state (e.g. the in-memory
vector store) are process-wide singletons. Selecting a provider that is not yet
wired raises a clear error rather than failing obscurely.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services.ingestion.chunking import Chunker
from app.services.ingestion.embedding import HashingEmbedder
from app.services.ingestion.parsers import LocalTextParser
from app.services.ingestion.ports import DocumentParser, Embedder
from app.services.storage import LocalFileStorage, ObjectStorage
from app.services.vectorstore import InMemoryVectorStore, VectorStore


@lru_cache
def get_parser() -> DocumentParser:
    provider = settings.parser_provider
    if provider == "local":
        return LocalTextParser()
    raise ServiceUnavailableError(f"Parser provider '{provider}' is not configured.")


@lru_cache
def get_embedder() -> Embedder:
    provider = settings.embedder_provider
    if provider == "hashing":
        return HashingEmbedder(dimension=settings.embedding_dimension)
    raise ServiceUnavailableError(f"Embedder provider '{provider}' is not configured.")


@lru_cache
def get_vector_store() -> VectorStore:
    provider = settings.vector_store_provider
    if provider == "memory":
        return InMemoryVectorStore()
    if provider == "qdrant":
        from app.services.vectorstore_qdrant import QdrantVectorStore

        api_key = settings.qdrant_api_key
        return QdrantVectorStore(
            url=settings.qdrant_url,
            api_key=api_key.get_secret_value() if api_key else None,
            collection=settings.qdrant_collection,
            dimension=settings.embedding_dimension,
        )
    raise ServiceUnavailableError(f"Vector store provider '{provider}' is not configured.")


@lru_cache
def get_storage() -> ObjectStorage:
    return LocalFileStorage(settings.storage_dir)


def get_chunker() -> Chunker:
    return Chunker(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
