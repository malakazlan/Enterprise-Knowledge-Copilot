"""Provider factories that resolve ingestion adapters from settings.

Each factory is memoised so implementations that hold state (e.g. the in-memory
vector store) are process-wide singletons. Selecting a provider that is not yet
wired raises a clear error rather than failing obscurely.
"""

from __future__ import annotations

from functools import lru_cache

import structlog

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services.ingestion.chunking import Chunker
from app.services.ingestion.embedding import HashingEmbedder
from app.services.ingestion.parsers import (
    CompositeParser,
    ImageOcrParser,
    LocalTextParser,
    PdfParser,
)
from app.services.ingestion.ports import DocumentParser, Embedder, OcrEngine
from app.services.storage import LocalFileStorage, ObjectStorage
from app.services.vectorstore import InMemoryVectorStore, VectorStore

logger = structlog.get_logger("app.ingestion.factory")


@lru_cache
def get_ocr() -> OcrEngine | None:
    provider = settings.ocr_provider
    if provider == "none":
        return None
    if provider == "rapidocr":
        try:
            import pypdfium2  # noqa: F401 - availability probe
            import rapidocr  # noqa: F401 - availability probe
        except ImportError as exc:
            raise ServiceUnavailableError(
                "OCR provider 'rapidocr' requires the ocr extras: "
                'pip install "enterprise-knowledge-copilot[ocr]"'
            ) from exc
        from app.services.ingestion.ocr import RapidOcrEngine

        return RapidOcrEngine(
            render_scale=settings.ocr_render_scale,
            min_line_confidence=settings.ocr_min_line_confidence,
        )
    raise ServiceUnavailableError(f"OCR provider '{provider}' is not configured.")


@lru_cache
def get_parser() -> DocumentParser:
    provider = settings.parser_provider
    if provider == "local":
        ocr: OcrEngine | None = None
        try:
            ocr = get_ocr()
        except ServiceUnavailableError as exc:
            # Text and digital-PDF ingestion still work without OCR; scanned
            # content will be rejected or fail loudly instead.
            logger.warning("ocr_unavailable", error=str(exc))

        # Order matters: specific binary formats first, generic text last.
        parsers: list[DocumentParser] = [PdfParser(ocr=ocr)]
        if ocr is not None:
            parsers.append(ImageOcrParser(ocr))
        import importlib.util

        if all(
            importlib.util.find_spec(module) is not None for module in ("docx", "pptx", "openpyxl")
        ):
            from app.services.ingestion.office import OfficeParser

            parsers.append(OfficeParser())
        else:
            # DOCX/PPTX/XLSX need the [office] extra; everything else works.
            logger.warning("office_parsers_unavailable")
        parsers.append(LocalTextParser())
        return CompositeParser(parsers)
    raise ServiceUnavailableError(f"Parser provider '{provider}' is not configured.")


@lru_cache
def get_embedder() -> Embedder:
    provider = settings.embedder_provider
    if provider == "hashing":
        return HashingEmbedder(dimension=settings.embedding_dimension)
    if provider == "openai":
        api_key = settings.openai_api_key
        if api_key is None:
            raise ServiceUnavailableError(
                "OPENAI_API_KEY is required when embedder_provider=openai."
            )
        from app.services.ingestion.embedding import OpenAIEmbedder

        return OpenAIEmbedder(
            api_key=api_key.get_secret_value(),
            model=settings.openai_embedding_model,
            dimension=settings.embedding_dimension,
            base_url=settings.openai_base_url,
        )
    if provider == "fastembed":
        from app.services.ingestion.embedding import FastEmbedEmbedder

        return FastEmbedEmbedder(model=settings.fastembed_model, cache_dir=settings.model_cache_dir)
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
            # Sized from the active embedder so switching providers can never
            # produce vectors that don't fit the collection.
            dimension=get_embedder().dimension,
        )
    raise ServiceUnavailableError(f"Vector store provider '{provider}' is not configured.")


@lru_cache
def get_storage() -> ObjectStorage:
    return LocalFileStorage(settings.storage_dir)


def get_chunker() -> Chunker:
    return Chunker(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)
