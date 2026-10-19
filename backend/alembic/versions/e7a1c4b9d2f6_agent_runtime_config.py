"""agent runtime config singleton

Revision ID: e7a1c4b9d2f6
Revises: c4f1a9e2b7d3
Create Date: 2026-10-19 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7a1c4b9d2f6"
down_revision: str | None = "c4f1a9e2b7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_config",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "max_total_tokens",
            sa.Integer(),
            server_default=sa.text("64000"),
            nullable=False,
        ),
        sa.Column(
            "compaction_threshold_tokens",
            sa.Integer(),
            server_default=sa.text("48000"),
            nullable=False,
        ),
        sa.Column(
            "max_steps",
            sa.Integer(),
            server_default=sa.text("8"),
            nullable=False,
        ),
        sa.Column(
            "max_tool_calls_per_turn",
            sa.Integer(),
            server_default=sa.text("6"),
            nullable=False,
        ),
        sa.Column(
            "max_parallel_tools",
            sa.Integer(),
            server_default=sa.text("6"),
            nullable=False,
        ),
        sa.Column(
            "max_tool_result_chars",
            sa.Integer(),
            server_default=sa.text("12000"),
            nullable=False,
        ),
        sa.Column(
            "max_total_tool_result_chars",
            sa.Integer(),
            server_default=sa.text("24000"),
            nullable=False,
        ),
        sa.Column(
            "max_page_context_chars",
            sa.Integer(),
            server_default=sa.text("6000"),
            nullable=False,
        ),
        sa.Column(
            "max_compaction_summary_chars",
            sa.Integer(),
            server_default=sa.text("6000"),
            nullable=False,
        ),
        sa.Column(
            "max_compaction_last_user_chars",
            sa.Integer(),
            server_default=sa.text("4000"),
            nullable=False,
        ),
        sa.Column(
            "auto_compaction_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "parallel_tools_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_agent_config_singleton")),
        sa.CheckConstraint(
            "max_total_tokens BETWEEN 8000 AND 200000",
            name=op.f("ck_agent_config_max_total_tokens_range"),
        ),
        sa.CheckConstraint(
            "compaction_threshold_tokens BETWEEN 1000 AND 200000",
            name=op.f("ck_agent_config_compaction_threshold_tokens_range"),
        ),
        sa.CheckConstraint(
            "max_steps BETWEEN 1 AND 32",
            name=op.f("ck_agent_config_max_steps_range"),
        ),
        sa.CheckConstraint(
            "max_tool_calls_per_turn BETWEEN 1 AND 24",
            name=op.f("ck_agent_config_max_tool_calls_per_turn_range"),
        ),
        sa.CheckConstraint(
            "max_parallel_tools BETWEEN 1 AND 24",
            name=op.f("ck_agent_config_max_parallel_tools_range"),
        ),
        sa.CheckConstraint(
            "max_tool_result_chars BETWEEN 1000 AND 100000",
            name=op.f("ck_agent_config_max_tool_result_chars_range"),
        ),
        sa.CheckConstraint(
            "max_total_tool_result_chars BETWEEN 1000 AND 200000",
            name=op.f("ck_agent_config_max_total_tool_result_chars_range"),
        ),
        sa.CheckConstraint(
            "max_page_context_chars BETWEEN 500 AND 50000",
            name=op.f("ck_agent_config_max_page_context_chars_range"),
        ),
        sa.CheckConstraint(
            "max_compaction_summary_chars BETWEEN 1000 AND 20000",
            name=op.f("ck_agent_config_max_compaction_summary_chars_range"),
        ),
        sa.CheckConstraint(
            "max_compaction_last_user_chars BETWEEN 500 AND 10000",
            name=op.f("ck_agent_config_max_compaction_last_user_chars_range"),
        ),
        sa.CheckConstraint(
            "compaction_threshold_tokens < max_total_tokens",
            name=op.f("ck_agent_config_compaction_below_total"),
        ),
        sa.CheckConstraint(
            "max_tool_result_chars <= max_total_tool_result_chars",
            name=op.f("ck_agent_config_tool_result_within_total"),
        ),
        sa.CheckConstraint(
            "max_parallel_tools <= max_tool_calls_per_turn",
            name=op.f("ck_agent_config_parallel_within_tool_calls"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_config")),
    )
    op.execute("INSERT INTO agent_config (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("agent_config")
