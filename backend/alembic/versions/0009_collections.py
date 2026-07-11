"""collections and document access

Revision ID: 0009_collections
Revises: 0008_chat_threads
Create Date: 2026-07-12 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009_collections"
down_revision: str | None = "0008_chat_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            name=op.f("fk_collections_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("name", name=op.f("uq_collections_name")),
    )

    op.create_table(
        "collection_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_members_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_collection_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_members")),
        sa.UniqueConstraint("collection_id", "user_id", name="uq_collection_members_pair"),
    )
    op.create_index(
        op.f("ix_collection_members_collection_id"), "collection_members", ["collection_id"]
    )
    op.create_index(op.f("ix_collection_members_user_id"), "collection_members", ["user_id"])

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_documents_collection_id"), ["collection_id"])
        batch_op.create_foreign_key(
            batch_op.f("fk_documents_collection_id_collections"),
            "collections",
            ["collection_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_documents_collection_id_collections"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_documents_collection_id"))
        batch_op.drop_column("collection_id")

    op.drop_index(op.f("ix_collection_members_user_id"), table_name="collection_members")
    op.drop_index(op.f("ix_collection_members_collection_id"), table_name="collection_members")
    op.drop_table("collection_members")
    op.drop_table("collections")
