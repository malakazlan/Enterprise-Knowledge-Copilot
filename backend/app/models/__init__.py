"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
metadata-driven tooling (Alembic autogenerate, test schema creation) sees them.
"""

from __future__ import annotations

from app.models.apikey import ApiKey
from app.models.document import (
    Document,
    DocumentChunk,
    IngestionJob,
    IngestionStatus,
    JobStage,
    JobStatus,
)
from app.models.querylog import QueryLog
from app.models.user import User, UserRole

__all__ = [
    "ApiKey",
    "Document",
    "DocumentChunk",
    "IngestionJob",
    "IngestionStatus",
    "JobStage",
    "JobStatus",
    "QueryLog",
    "User",
    "UserRole",
]
