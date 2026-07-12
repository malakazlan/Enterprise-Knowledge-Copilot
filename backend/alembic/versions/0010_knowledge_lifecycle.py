"""knowledge lifecycle

Revision ID: 0010_knowledge_lifecycle
Revises: 0009_collections
Create Date: 2026-07-12 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0010_knowledge_lifecycle"
down_revision: str | None = "0009_collections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("verify_by", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_documents_verify_by"), ["verify_by"])


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_verify_by"))
        batch_op.drop_column("verify_by")
