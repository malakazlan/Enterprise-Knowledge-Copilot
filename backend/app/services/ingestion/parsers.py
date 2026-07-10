"""Document parsers.

``LocalTextParser`` handles text-based formats (markdown, plain text, CSV,
JSON) with no external dependency — genuinely useful for SOPs/manuals and
enough to exercise the full pipeline. Layout-aware parsers for PDF/scans
(LlamaParse, Docling, OCR) implement the same port and are added next.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.ingestion.ports import ParsedDocument, ParsedPage

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
