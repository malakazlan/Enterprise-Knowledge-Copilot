"""Document parsers.

- ``LocalTextParser`` — text formats (markdown, plain text, CSV, JSON).
- ``PdfParser`` — digital PDFs via ``pypdf``, page-accurate extraction.
- ``CompositeParser`` — routes each file to the first parser that supports it
  and rejects unsupported types loudly instead of mangling binary content.

Layout-aware parsing for scans (Docling, LlamaParse, OCR) implements the same
port and slots into the composite chain when configured.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pypdf import PdfReader

from app.services.ingestion.ports import (
    DocumentParser,
    OcrEngine,
    ParsedDocument,
    ParsedPage,
)

_TEXT_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/csv",
        "text/html",
        "application/json",
        "application/xml",
    }
)
_TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".log", ".rst", ".html"}
)


class LocalTextParser:
    name = "local-text"

    def supports(self, content_type: str, filename: str) -> bool:
        extension = Path(filename).suffix.lower()
        return content_type in _TEXT_CONTENT_TYPES or extension in _TEXT_EXTENSIONS

    async def parse(self, *, file_path: str, content_type: str, filename: str) -> ParsedDocument:
        data = await asyncio.to_thread(Path(file_path).read_bytes)
        text = data.decode("utf-8", errors="replace")

        # Honour form-feed page breaks if present; otherwise treat as one page.
        raw_pages = text.split("\f") if "\f" in text else [text]
        pages = [
            ParsedPage(page_number=number, text=content)
            for number, content in enumerate(raw_pages, start=1)
        ]
        return ParsedDocument(
            pages=pages,
            title=Path(filename).stem,
            metadata={"parser": self.name, "content_type": content_type},
        )


class PdfParser:
    """PDF parser (pypdf) with per-page OCR fallback.

    The embedded text layer is used when present; pages without one (scans)
    are routed to the configured OCR engine. Mixed digital/scanned PDFs — the
    enterprise norm — therefore work page by page. OCR'd pages and their mean
    confidence are recorded in the document metadata so low-quality scans can
    be surfaced for human review.
    """

    name = "pypdf"

    # Text layers with fewer meaningful characters than this are treated as
    # absent (scanned pages often carry a few stray artifacts).
    _MIN_TEXT_LAYER_CHARS = 4

    def __init__(self, ocr: OcrEngine | None = None) -> None:
        self._ocr = ocr

    def supports(self, content_type: str, filename: str) -> bool:
        return content_type == "application/pdf" or Path(filename).suffix.lower() == ".pdf"

    async def parse(self, *, file_path: str, content_type: str, filename: str) -> ParsedDocument:
        def _read() -> tuple[list[ParsedPage], str | None, list[int], list[float]]:
            reader = PdfReader(file_path)
            pages: list[ParsedPage] = []
            ocr_pages: list[int] = []
            confidences: list[float] = []
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if len(text.strip()) < self._MIN_TEXT_LAYER_CHARS and self._ocr is not None:
                    result = self._ocr.recognize_pdf_page(file_path, number - 1)
                    if result.text:
                        text = result.text
                        ocr_pages.append(number)
                        confidences.append(result.confidence)
                pages.append(ParsedPage(page_number=number, text=text))
            meta = reader.metadata
            title = meta.title if meta is not None and meta.title else None
            return pages, title, ocr_pages, confidences

        # pypdf and OCR are synchronous and CPU bound — keep off the event loop.
        pages, title, ocr_pages, confidences = await asyncio.to_thread(_read)
        metadata: dict[str, object] = {"parser": self.name, "content_type": content_type}
        if ocr_pages:
            metadata["ocr_engine"] = self._ocr.name if self._ocr else None
            metadata["ocr_pages"] = ocr_pages
            # Minimum across pages: one bad page should flag the document.
            metadata["ocr_confidence"] = min(confidences)
        return ParsedDocument(
            pages=pages,
            title=title or Path(filename).stem,
            metadata=metadata,
        )


_IMAGE_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp"}
)
_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"})


class ImageOcrParser:
    """Single-page scanned images (photographed or scanned documents)."""

    name = "image-ocr"

    def __init__(self, ocr: OcrEngine) -> None:
        self._ocr = ocr

    def supports(self, content_type: str, filename: str) -> bool:
        extension = Path(filename).suffix.lower()
        return content_type in _IMAGE_CONTENT_TYPES or extension in _IMAGE_EXTENSIONS

    async def parse(self, *, file_path: str, content_type: str, filename: str) -> ParsedDocument:
        result = await asyncio.to_thread(self._ocr.recognize_image, file_path)
        return ParsedDocument(
            pages=[ParsedPage(page_number=1, text=result.text)],
            title=Path(filename).stem,
            metadata={
                "parser": self.name,
                "content_type": content_type,
                "ocr_engine": self._ocr.name,
                "ocr_pages": [1],
                "ocr_confidence": result.confidence,
            },
        )


class CompositeParser:
    """Routes to the first parser in the chain that supports the file."""

    name = "composite"

    def __init__(self, parsers: list[DocumentParser]) -> None:
        self._parsers = parsers

    def supports(self, content_type: str, filename: str) -> bool:
        return any(parser.supports(content_type, filename) for parser in self._parsers)

    async def parse(self, *, file_path: str, content_type: str, filename: str) -> ParsedDocument:
        for parser in self._parsers:
            if parser.supports(content_type, filename):
                return await parser.parse(
                    file_path=file_path, content_type=content_type, filename=filename
                )
        raise ValueError(f"Unsupported file type: {filename} ({content_type}).")
