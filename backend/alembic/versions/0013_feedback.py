"""answer feedback

Revision ID: 0013_feedback
Revises: 0012_agent_memories
Create Date: 2026-07-14 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0013_feedback"
down_revision: str | None = "0012_agent_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("query_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("feedback", sa.String(length=12), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("query_logs", schema=None) as batch_op:
        batch_op.drop_column("feedback")
