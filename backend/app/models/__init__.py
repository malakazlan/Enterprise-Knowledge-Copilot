"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
metadata-driven tooling (Alembic autogenerate, test schema creation) sees them.
"""

from __future__ import annotations

from app.models.apikey import ApiKey
from app.models.collection import Collection, CollectionMember
from app.models.document import (
    Document,
    DocumentChunk,
    IngestionJob,
    IngestionStatus,
    JobStage,
    JobStatus,
)
from app.models.evals import EvalCase, EvalDataset, EvalRun
from app.models.querylog import QueryLog, ReviewStatus
from app.models.thread import ChatThread
from app.models.user import User, UserRole
from app.models.webhook import WEBHOOK_EVENTS, Webhook

__all__ = [
    "WEBHOOK_EVENTS",
    "ApiKey",
    "ChatThread",
    "Collection",
    "CollectionMember",
    "Document",
    "DocumentChunk",
    "EvalCase",
    "EvalDataset",
    "EvalRun",
    "IngestionJob",
    "IngestionStatus",
    "JobStage",
    "JobStatus",
    "QueryLog",
    "ReviewStatus",
    "User",
    "UserRole",
    "Webhook",
]
