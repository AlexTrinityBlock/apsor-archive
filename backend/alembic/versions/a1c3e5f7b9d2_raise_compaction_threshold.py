"""raise the auto-compaction threshold cap

Revision ID: a1c3e5f7b9d2
Revises: a4c8e2f6b9d1
Create Date: 2026-11-01 00:00:00.000000

The active context can now be much larger than 200k tokens. Keep the
``compaction_threshold_tokens < context_window_tokens`` invariant while
allowing the threshold itself to reach 1,000,000.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: str | None = "a4c8e2f6b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow the compaction threshold to reach one million tokens."""
    op.drop_constraint(
        op.f("ck_agent_config_compaction_threshold_tokens_range"),
        "agent_config",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_threshold_tokens_range"),
        "agent_config",
        "compaction_threshold_tokens BETWEEN 1000 AND 1000000",
    )


def downgrade() -> None:
    """Restore the former 200k threshold cap."""
    op.drop_constraint(
        op.f("ck_agent_config_compaction_threshold_tokens_range"),
        "agent_config",
        type_="check",
    )
    op.execute(
        "UPDATE agent_config SET compaction_threshold_tokens = "
        "LEAST(compaction_threshold_tokens, 200000)"
    )
    op.create_check_constraint(
        op.f("ck_agent_config_compaction_threshold_tokens_range"),
        "agent_config",
        "compaction_threshold_tokens BETWEEN 1000 AND 200000",
    )
