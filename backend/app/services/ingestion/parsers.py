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

from app.services.ingestion.ports import DocumentParser, ParsedDocument, ParsedPage

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
    """Digital-PDF parser (pypdf). Page numbers map 1:1 to the source file.

    Extracts the embedded text layer; scanned/image-only PDFs yield empty
    pages and fail ingestion with a clear error (OCR is a separate adapter).
    """

    name = "pypdf"

    def supports(self, content_type: str, filename: str) -> bool:
        return content_type == "application/pdf" or Path(filename).suffix.lower() == ".pdf"

    async def parse(self, *, file_path: str, content_type: str, filename: str) -> ParsedDocument:
        def _read() -> tuple[list[ParsedPage], str | None]:
            reader = PdfReader(file_path)
            pages = [
                ParsedPage(page_number=number, text=page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            ]
            meta = reader.metadata
            title = meta.title if meta is not None and meta.title else None
            return pages, title

        # pypdf is synchronous and CPU/IO bound — keep it off the event loop.
        pages, title = await asyncio.to_thread(_read)
        return ParsedDocument(
            pages=pages,
            title=title or Path(filename).stem,
            metadata={"parser": self.name, "content_type": content_type},
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
