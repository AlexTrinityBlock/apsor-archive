"""agent approvals for confirmation-required writes

Revision ID: f2b3c4d5e6a7
Revises: c8f2a4b6d9e1
Create Date: 2026-10-19 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2b3c4d5e6a7"
down_revision: str | None = "c8f2a4b6d9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_approval",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "arguments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "preview",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "resume_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("resolved_by_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name=op.f("ck_agent_approval_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversation.id"],
            name=op.f("fk_agent_approval_conversation_id_agent_conversation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_entry_id"],
            ["agent_entry.id"],
            name=op.f("fk_agent_approval_resolved_by_entry_id_agent_entry"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_run.id"],
            name=op.f("fk_agent_approval_run_id_agent_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_approval")),
    )
    op.create_index(
        "ix_agent_approval_conversation_status",
        "agent_approval",
        ["conversation_id", "status", "id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_approval_run_status",
        "agent_approval",
        ["run_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_agent_approval_pending_call",
        "agent_approval",
        ["run_id", "tool_call_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_approval_pending_call", table_name="agent_approval")
    op.drop_index("ix_agent_approval_run_status", table_name="agent_approval")
    op.drop_index(
        "ix_agent_approval_conversation_status",
        table_name="agent_approval",
    )
    op.drop_table("agent_approval")
