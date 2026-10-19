"""saved questions Q&A library

Revision ID: b7d2e9c4a1f6
Revises: c9f1a2b3d4e5
Create Date: 2026-10-19 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7d2e9c4a1f6"
down_revision: str | None = "c9f1a2b3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_question",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("run_status", sa.String(length=16), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
        sa.Column("last_asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 1 AND 32000",
            name=op.f("ck_saved_question_question_length"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(citations) = 'array'",
            name=op.f("ck_saved_question_citations_array"),
        ),
        sa.CheckConstraint(
            "run_status IS NULL OR run_status IN "
            "('running', 'waiting', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_saved_question_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversation.id"],
            name=op.f("fk_saved_question_conversation_id_agent_conversation"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_question")),
    )
    op.create_index(
        "ix_saved_question_conversation_id",
        "saved_question",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_question_conversation_id", table_name="saved_question")
    op.drop_table("saved_question")
