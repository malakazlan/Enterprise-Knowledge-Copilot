"""CPU-tier OCR adapter (RapidOCR / PP-OCRv5+ ONNX models).

Classic OCR engines lose most of their accuracy to *engineering* problems,
not recognition problems. This adapter closes those gaps:

- **High-DPI rasterization** — PDF pages render at ``render_scale`` (3.0 ≈
  216 dpi) via pypdfium2; low-resolution rendering is the #1 cause of missed
  text on scanned PDFs.
- **Confidence gating** — lines below ``min_line_confidence`` are dropped
  instead of polluting the search index with junk; the mean confidence of the
  kept lines is reported so low-quality documents can be flagged for review.
- **Reading-order reconstruction** — detected boxes are grouped into rows by
  vertical overlap and sorted top-to-bottom, left-to-right, so the chunker
  receives coherent text instead of detector-order fragments.

Heavy dependencies (rapidocr, pypdfium2) are imported lazily inside methods so
the module is importable without the ``[ocr]`` extras installed. A GPU-tier
VLM OCR adapter implements the same :class:`OcrEngine` port later.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.ingestion.ports import OcrResult


def assemble_lines(
    entries: list[tuple[str, float, list[tuple[float, float]]]],
    *,
    min_confidence: float,
) -> OcrResult:
    """Build reading-ordered text from raw ``(text, score, box)`` detections.

    Boxes are 4-point polygons. Lines are grouped into rows when their
    vertical centers overlap within 60% of the taller line's height, then
    rows read left-to-right and stack top-to-bottom.
    """
    items: list[tuple[float, float, float, str, float]] = []
    for text, score, box in entries:
        if score < min_confidence or not text.strip():
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        top, bottom = min(ys), max(ys)
        items.append(((top + bottom) / 2, bottom - top, min(xs), text.strip(), score))

    if not items:
        return OcrResult(text="", confidence=0.0)

    items.sort(key=lambda item: item[0])
    rows: list[dict[str, Any]] = []
    for y_center, height, x_left, text, _score in items:
        if rows and abs(y_center - rows[-1]["y"]) <= 0.6 * max(height, rows[-1]["h"]):
            rows[-1]["cells"].append((x_left, text))
        else:
            rows.append({"y": y_center, "h": height, "cells": [(x_left, text)]})

    lines = []
    for row in rows:
        row["cells"].sort(key=lambda cell: cell[0])
        lines.append(" ".join(text for _, text in row["cells"]))

    confidence = sum(item[4] for item in items) / len(items)
    return OcrResult(text="\n".join(lines), confidence=round(confidence, 4))


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self, *, render_scale: float, min_line_confidence: float) -> None:
        self._render_scale = render_scale
        self._min_line_confidence = min_line_confidence
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            from rapidocr import RapidOCR  # heavy import deferred

            self._engine = RapidOCR()
        return self._engine

    def _run(self, image: Any) -> OcrResult:
        result = self._get_engine()(image)
        if not result.txts:
            return OcrResult(text="", confidence=0.0)
        entries = list(zip(result.txts, result.scores, result.boxes, strict=True))
        return assemble_lines(entries, min_confidence=self._min_line_confidence)

    def recognize_pdf_page(self, file_path: str, page_index: int) -> OcrResult:
        import pypdfium2 as pdfium  # heavy import deferred

        document = pdfium.PdfDocument(file_path)
        try:
            bitmap = document[page_index].render(scale=self._render_scale)
            image = bitmap.to_numpy()
        finally:
            document.close()
        return self._run(image)

    def recognize_image(self, file_path: str) -> OcrResult:
        return self._run(file_path)
