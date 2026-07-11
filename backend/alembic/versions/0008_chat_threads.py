"""chat threads

Revision ID: 0008_chat_threads
Revises: 0007_webhooks
Create Date: 2026-07-12 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008_chat_threads"
down_revision: str | None = "0007_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_chat_threads_created_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
    )
    op.create_index(op.f("ix_chat_threads_created_by"), "chat_threads", ["created_by"])

    with op.batch_alter_table("query_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("thread_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_query_logs_thread_id"), ["thread_id"])
        batch_op.create_foreign_key(
            batch_op.f("fk_query_logs_thread_id_chat_threads"),
            "chat_threads",
            ["thread_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("query_logs", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_query_logs_thread_id_chat_threads"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_query_logs_thread_id"))
        batch_op.drop_column("thread_id")

    op.drop_index(op.f("ix_chat_threads_created_by"), table_name="chat_threads")
    op.drop_table("chat_threads")
