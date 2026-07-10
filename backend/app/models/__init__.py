"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
metadata-driven tooling (Alembic autogenerate, test schema creation) sees them.
"""

from __future__ import annotations

from app.models.user import User, UserRole

__all__ = ["User", "UserRole"]
