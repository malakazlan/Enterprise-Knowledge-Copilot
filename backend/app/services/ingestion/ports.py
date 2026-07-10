"""Value objects and provider ports for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str


@dataclass(slots=True)
class ParsedDocument:
    pages: list[ParsedPage]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


@dataclass(slots=True)
class ChunkData:
    index: int
    content: str
    page_number: int | None
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DocumentParser(Protocol):
    """Turns a raw file into page-structured text for citation."""

    name: str

    def supports(self, content_type: str, filename: str) -> bool: ...
    async def parse(
        self, *, file_path: str, content_type: str, filename: str
    ) -> ParsedDocument: ...


@runtime_checkable
class Embedder(Protocol):
    """Produces dense vector embeddings for text."""

    name: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
