"""Tests for the PDF parser, composite routing, and end-to-end PDF ingestion."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services.ingestion.embedding import OpenAIEmbedder
from app.services.ingestion.parsers import CompositeParser, LocalTextParser, PdfParser
from tests.pdf_fixtures import make_pdf

DOCUMENTS = "/api/v1/documents"
SEARCH = "/api/v1/search"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]


# --- PdfParser unit ---


async def test_pdf_parser_extracts_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(make_pdf(["Helmets are mandatory on site.", "Invoices are due monthly."]))

    parsed = await PdfParser().parse(
        file_path=str(pdf_path), content_type="application/pdf", filename="doc.pdf"
    )
    assert parsed.page_count == 2
    assert parsed.pages[0].page_number == 1
    assert "Helmets" in parsed.pages[0].text
    assert parsed.pages[1].page_number == 2
    assert "Invoices" in parsed.pages[1].text


def test_pdf_parser_supports() -> None:
    parser = PdfParser()
    assert parser.supports("application/pdf", "x.bin")
    assert parser.supports("application/octet-stream", "scan.PDF")
    assert not parser.supports("text/plain", "notes.txt")


# --- Composite routing ---


def test_composite_routes_by_support() -> None:
    composite = CompositeParser([PdfParser(), LocalTextParser()])
    assert composite.supports("application/pdf", "a.pdf")
    assert composite.supports("text/markdown", "a.md")
    assert not composite.supports("application/zip", "a.zip")


async def test_composite_rejects_unsupported(tmp_path: Path) -> None:
    blob = tmp_path / "a.zip"
    blob.write_bytes(b"PK\x03\x04 not really a zip")
    composite = CompositeParser([PdfParser(), LocalTextParser()])
    with pytest.raises(ValueError, match="Unsupported file type"):
        await composite.parse(file_path=str(blob), content_type="application/zip", filename="a.zip")


# --- End-to-end: upload PDF -> search with page citations ---


async def test_pdf_upload_is_searchable_with_page_numbers(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    pdf = make_pdf(
        ["All workers must wear a helmet on the construction site.", "Invoices are due by the 5th."]
    )
    upload = await client.post(
        DOCUMENTS, headers=headers, files={"file": ("manual.pdf", pdf, "application/pdf")}
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["document"]["status"] == "completed"
    assert body["document"]["page_count"] == 2

    search = await client.post(SEARCH, headers=headers, json={"query": "helmet construction"})
    results = search.json()["results"]
    assert results, "expected PDF content to be retrievable"
    top = results[0]
    assert top["filename"] == "manual.pdf"
    assert top["page_number"] == 1  # citation points at the right page

    search2 = await client.post(SEARCH, headers=headers, json={"query": "invoices due"})
    top2 = search2.json()["results"][0]
    assert top2["page_number"] == 2


async def test_unsupported_upload_rejected_early(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")
    resp = await client.post(
        DOCUMENTS,
        headers=headers,
        files={"file": ("archive.zip", b"PK\x03\x04binary", "application/zip")},
    )
    assert resp.status_code == 422
    assert "Unsupported file type" in resp.json()["error"]["message"]


# --- OpenAI embeddings adapter (wire format via mocked transport) ---


async def test_openai_embedder_request_and_ordering() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        # Return results deliberately out of order to prove re-sorting.
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    embedder = OpenAIEmbedder(
        api_key="sk-test",
        model="text-embedding-3-small",
        dimension=2,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    vectors = await embedder.embed(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]  # re-ordered by index
    body = captured["body"]
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["first", "second"]
    assert body["dimensions"] == 2
    assert await embedder.embed([]) == []
