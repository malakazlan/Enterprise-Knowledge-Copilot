"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
metadata-driven tooling (Alembic autogenerate, test schema creation) sees them.
"""

from __future__ import annotations

from app.models.apikey import ApiKey
from app.models.collection import Collection, CollectionMember
from app.models.connector import CONNECTOR_TYPES, Connector
from app.models.document import (
    Document,
    DocumentChunk,
    IngestionJob,
    IngestionStatus,
    JobStage,
    JobStatus,
)
from app.models.evals import EvalCase, EvalDataset, EvalRun
from app.models.memory import MEMORY_KINDS, AgentMemory
from app.models.querylog import QueryLog, ReviewStatus
from app.models.thread import ChatThread
from app.models.user import User, UserRole
from app.models.webhook import WEBHOOK_EVENTS, Webhook

__all__ = [
    "CONNECTOR_TYPES",
    "MEMORY_KINDS",
    "WEBHOOK_EVENTS",
    "AgentMemory",
    "ApiKey",
    "ChatThread",
    "Collection",
    "CollectionMember",
    "Connector",
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
