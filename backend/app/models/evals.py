"""Evaluation datasets, cases, and runs.

A dataset is a golden set of questions with expected evidence; a run scores
the current pipeline configuration against it. Runs are the measurement layer
behind every accuracy claim — and the feedback signal for profile tuning.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EvalDataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eval_datasets"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Profile evaluated by default; runs may override. Null -> deployment default.
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class EvalCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eval_cases"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Retrieval ground truth: the document (and optionally page) that must be found.
    expected_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    expected_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Answer ground truth: facts the answer must contain (case-insensitive).
    expected_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class EvalRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eval_runs"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    profile: Mapped[str] = mapped_column(String(64), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Aggregate metrics (hit_rate, mrr, citation_accuracy, ...).
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Per-case detail rows for drill-down.
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
