"""Tests for the CPU-tier OCR adapter and per-page OCR routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import cv2
import numpy as np
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.services.ingestion.ocr import RapidOcrEngine, assemble_lines
from app.services.ingestion.parsers import PdfParser
from app.services.ingestion.ports import OcrResult
from tests.pdf_fixtures import make_pdf

DOCUMENTS = "/api/v1/documents"
SEARCH = "/api/v1/search"

MakeUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[..., Awaitable[dict[str, str]]]


def _scan_image(lines: list[str]) -> np.ndarray:
    """Synthesize a scanned page: white background, large black text."""
    image = np.full((160 + 140 * len(lines), 1400, 3), 255, dtype=np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(image, line, (40, 120 + 140 * i), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
    return image


# --- assemble_lines (pure engineering layer) ---


def _box(top: float, left: float, *, h: float = 20, w: float = 200) -> list[tuple[float, float]]:
    return [(left, top), (left + w, top), (left + w, top + h), (left, top + h)]


def test_assemble_lines_restores_reading_order() -> None:
    # Detector returns fragments out of order; same row cells + stacked rows.
    entries = [
        ("beta", 0.95, _box(100, 400)),  # row 1, right cell
        ("gamma", 0.99, _box(200, 40)),  # row 2
        ("alpha", 0.97, _box(102, 40)),  # row 1, left cell (2px jitter)
    ]
    result = assemble_lines(entries, min_confidence=0.5)
    assert result.text == "alpha beta\ngamma"
    assert 0.95 < result.confidence <= 1.0


def test_assemble_lines_drops_low_confidence_junk() -> None:
    entries = [
        ("real text", 0.98, _box(10, 10)),
        (")(*&^ garbage", 0.21, _box(60, 10)),  # below threshold -> dropped
        ("   ", 0.99, _box(110, 10)),  # whitespace -> dropped
    ]
    result = assemble_lines(entries, min_confidence=0.5)
    assert result.text == "real text"
    assert result.confidence == 0.98


def test_assemble_lines_empty() -> None:
    assert assemble_lines([], min_confidence=0.5) == OcrResult(text="", confidence=0.0)


# --- Real engine on a synthetic scan ---


def test_rapidocr_reads_synthetic_scan(tmp_path: Path) -> None:
    image_path = tmp_path / "scan.png"
    cv2.imwrite(str(image_path), _scan_image(["HELMETS ARE REQUIRED ON SITE"]))

    engine = RapidOcrEngine(render_scale=3.0, min_line_confidence=0.5)
    result = engine.recognize_image(str(image_path))
    assert "HELMETS" in result.text.upper()
    assert result.confidence > 0.8


# --- Per-page routing inside PdfParser ---


class FakeOcr:
    name = "fake-ocr"

    def __init__(self) -> None:
        self.pdf_calls: list[int] = []

    def recognize_pdf_page(self, file_path: str, page_index: int) -> OcrResult:
        self.pdf_calls.append(page_index)
        return OcrResult(text="OCR RECOVERED TEXT", confidence=0.77)

    def recognize_image(self, file_path: str) -> OcrResult:
        return OcrResult(text="", confidence=0.0)


async def test_pdf_parser_routes_only_textless_pages_to_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "mixed.pdf"
    pdf_path.write_bytes(make_pdf(["This page has a digital text layer.", ""]))

    fake = FakeOcr()
    parsed = await PdfParser(ocr=fake).parse(
        file_path=str(pdf_path), content_type="application/pdf", filename="mixed.pdf"
    )

    assert fake.pdf_calls == [1]  # only the empty page (0-based index 1)
    assert "digital text layer" in parsed.pages[0].text
    assert parsed.pages[1].text == "OCR RECOVERED TEXT"
    assert parsed.metadata["ocr_pages"] == [2]
    assert parsed.metadata["ocr_confidence"] == 0.77


async def test_pdf_parser_without_ocr_leaves_pages_empty(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanonly.pdf"
    pdf_path.write_bytes(make_pdf([""]))
    parsed = await PdfParser(ocr=None).parse(
        file_path=str(pdf_path), content_type="application/pdf", filename="scanonly.pdf"
    )
    assert parsed.pages[0].text == ""
    assert "ocr_pages" not in parsed.metadata


# --- End-to-end: scanned image upload -> OCR -> searchable ---


async def test_scanned_image_upload_is_searchable(
    client: AsyncClient, make_user: MakeUser, auth_headers: AuthHeaders
) -> None:
    await make_user("admin@example.com", role=UserRole.ADMIN)
    headers = await auth_headers("admin@example.com")

    ok, encoded = cv2.imencode(".png", _scan_image(["HELMETS ARE REQUIRED ON SITE"]))
    assert ok

    upload = await client.post(
        DOCUMENTS,
        headers=headers,
        files={"file": ("site-notice.png", encoded.tobytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    document = upload.json()["document"]
    assert document["status"] == "completed"
    assert document["doc_metadata"]["ocr_pages"] == [1]
    assert document["doc_metadata"]["ocr_confidence"] > 0.8

    search = await client.post(SEARCH, headers=headers, json={"query": "helmets required"})
    results = search.json()["results"]
    assert results and results[0]["filename"] == "site-notice.png"
    assert results[0]["page_number"] == 1
