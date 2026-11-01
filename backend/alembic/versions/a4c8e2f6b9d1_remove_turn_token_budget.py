"""remove the turn token budget

Revision ID: a4c8e2f6b9d1
Revises: f9c2a7d4e6b1
Create Date: 2026-10-29 00:00:00.000000

The turn loop no longer aborts on cumulative provider usage. Compaction is the
long-conversation control, and it is now measured against the model context
window instead of a separate per-turn ceiling.

Upgrade repairs any stored threshold that is not below its context window
before adding the replacement check constraint. Downgrade restores a 100,000
token ceiling, raising it when the stored threshold would otherwise violate the
old ``threshold < max_total_tokens`` rule.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4c8e2f6b9d1"
down_revision: str | None = "f9c2a7d4e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the per-turn token ceiling and bound compaction by context."""
    op.execute(
        "UPDATE agent_config SET compaction_threshold_tokens = "
        "GREATEST(1000, context_window_tokens - 1000) "
        "WHERE compaction_threshold_tokens >= context_window_tokens"
    )
    op.drop_constraint(
        op.f("ck_agent_config_compaction_below_total"),
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_config_max_total_tokens_range"),
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "max_total_tokens")
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_below_context"),
        "agent_config",
        "compaction_threshold_tokens < context_window_tokens",
    )


def downgrade() -> None:
    """Restore the legacy per-turn token ceiling."""
    op.drop_constraint(
        op.f("ck_agent_config_compaction_below_context"),
        "agent_config",
        type_="check",
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "max_total_tokens",
            sa.Integer(),
            server_default=sa.text("100000"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE agent_config SET compaction_threshold_tokens = 199000 "
        "WHERE compaction_threshold_tokens >= 200000"
    )
    op.execute(
        "UPDATE agent_config SET max_total_tokens = "
        "GREATEST(100000, LEAST(compaction_threshold_tokens + 1000, 200000))"
    )
    op.create_check_constraint(
        op.f("ck_agent_config_max_total_tokens_range"),
        "agent_config",
        "max_total_tokens BETWEEN 8000 AND 200000",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_below_total"),
        "agent_config",
        "compaction_threshold_tokens < max_total_tokens",
    )
