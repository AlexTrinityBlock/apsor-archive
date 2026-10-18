"""agent conversations

Revision ID: a7c41e9d2b60
Revises: f3cd26ca9f67
Create Date: 2026-10-18 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c41e9d2b60"
down_revision: str | None = "f3cd26ca9f67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE agent_commit_seq")

    op.create_table(
        "agent_conversation",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("parent_conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("fork_at_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("provider_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_entry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name=op.f("ck_agent_conversation_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_conversation_id"],
            ["agent_conversation.id"],
            name=op.f("fk_agent_conversation_parent_conversation_id_agent_conversation"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_conversation")),
        sa.UniqueConstraint(
            "provider_session_id",
            name=op.f("uq_agent_conversation_provider_session_id"),
        ),
    )
    op.create_index(
        "ix_agent_conversation_last_entry_at",
        "agent_conversation",
        ["last_entry_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_conversation_status",
        "agent_conversation",
        ["status"],
        unique=False,
    )

    op.create_table(
        "agent_entry",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "commit_seq",
            sa.BigInteger(),
            server_default=sa.text("nextval('agent_commit_seq'::regclass)"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("model", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("head_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("edits", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("by_run_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system', "
            "'pi.reset', 'pi.compaction', 'ui.notice')",
            name=op.f("ck_agent_entry_kind_valid"),
        ),
        sa.CheckConstraint(
            "kind NOT IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system') "
            "OR model IS NOT NULL",
            name=op.f("ck_agent_entry_model_required"),
        ),
        sa.CheckConstraint(
            "kind <> 'pi.tool-result' OR model->0->>'tool_call_id' IS NOT NULL",
            name=op.f("ck_agent_entry_tool_result_call_id"),
        ),
        sa.CheckConstraint(
            "edits IS NULL OR jsonb_typeof(edits) = 'array'",
            name=op.f("ck_agent_entry_edits_array"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversation.id"],
            name=op.f("fk_agent_entry_conversation_id_agent_conversation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["head_entry_id"],
            ["agent_entry.id"],
            name=op.f("fk_agent_entry_head_entry_id_agent_entry"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_entry")),
    )
    op.create_index(
        "ix_agent_entry_conversation_id",
        "agent_entry",
        ["conversation_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_entry_conversation_commit",
        "agent_entry",
        ["conversation_id", "commit_seq"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX ix_agent_entry_head ON agent_entry (conversation_id, id DESC) "
        "WHERE head_entry_id IS NOT NULL"
    )

    op.create_table(
        "agent_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("user_entry_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "abort_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'waiting', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_agent_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversation.id"],
            name=op.f("fk_agent_run_conversation_id_agent_conversation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_entry_id"],
            ["agent_entry.id"],
            name=op.f("fk_agent_run_last_entry_id_agent_entry"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_entry_id"],
            ["agent_entry.id"],
            name=op.f("fk_agent_run_user_entry_id_agent_entry"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_run")),
    )
    op.create_index(
        "ix_agent_run_conversation_id",
        "agent_run",
        ["conversation_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_run_conversation_status",
        "agent_run",
        ["conversation_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_agent_run_request",
        "agent_run",
        ["conversation_id", "request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
    )
    op.create_index(
        "uq_agent_run_running",
        "agent_run",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_foreign_key(
        "fk_agent_conversation_fork_at_entry_id_agent_entry",
        "agent_conversation",
        "agent_entry",
        ["fork_at_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_entry_by_run_id_agent_run",
        "agent_entry",
        "agent_run",
        ["by_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_entry_by_run_id_agent_run",
        "agent_entry",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_conversation_fork_at_entry_id_agent_entry",
        "agent_conversation",
        type_="foreignkey",
    )
    op.drop_index("uq_agent_run_running", table_name="agent_run")
    op.drop_index("uq_agent_run_request", table_name="agent_run")
    op.drop_index("ix_agent_run_conversation_status", table_name="agent_run")
    op.drop_index("ix_agent_run_conversation_id", table_name="agent_run")
    op.drop_table("agent_run")
    op.drop_index("ix_agent_entry_head", table_name="agent_entry")
    op.drop_index("ix_agent_entry_conversation_commit", table_name="agent_entry")
    op.drop_index("ix_agent_entry_conversation_id", table_name="agent_entry")
    op.drop_table("agent_entry")
    op.drop_index("ix_agent_conversation_status", table_name="agent_conversation")
    op.drop_index("ix_agent_conversation_last_entry_at", table_name="agent_conversation")
    op.drop_table("agent_conversation")
    op.execute("DROP SEQUENCE agent_commit_seq")
