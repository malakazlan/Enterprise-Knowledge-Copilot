"""Evaluation dataset/case/run schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    # Profile evaluated by default; None -> deployment default at run time.
    profile: str | None = None


class EvalDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    profile: str | None
    created_at: datetime


class EvalCaseCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    expected_document_id: uuid.UUID | None = None
    expected_page: int | None = Field(default=None, ge=1)
    expected_keywords: list[str] = Field(default_factory=list, max_length=50)


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    question: str
    expected_document_id: uuid.UUID | None
    expected_page: int | None
    expected_keywords: list[str]
    created_at: datetime


class EvalDatasetDetail(EvalDatasetRead):
    cases: list[EvalCaseRead]


class EvalRunRequest(BaseModel):
    # Overrides the dataset's profile for this run (A/B profile comparisons).
    profile: str | None = None


class EvalRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    profile: str
    case_count: int
    metrics: dict[str, Any]
    results: list[dict[str, Any]]
    created_at: datetime
