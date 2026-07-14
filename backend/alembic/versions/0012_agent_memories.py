"""agent memories

Revision ID: 0012_agent_memories
Revises: 0011_connectors
Create Date: 2026-07-14 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0012_agent_memories"
down_revision: str | None = "0011_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_memories")),
    )
    op.create_index(op.f("ix_agent_memories_scope"), "agent_memories", ["scope"])
    op.create_index(op.f("ix_agent_memories_expires_at"), "agent_memories", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_memories_expires_at"), table_name="agent_memories")
    op.drop_index(op.f("ix_agent_memories_scope"), table_name="agent_memories")
    op.drop_table("agent_memories")
