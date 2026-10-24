"""raise the turn token budget

Revision ID: c9f1a2b3d4e5
Revises: a6e2f9c4d1b8
Create Date: 2026-10-19 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9f1a2b3d4e5"
down_revision: str | None = "a6e2f9c4d1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Raise the cumulative turn budget and its compaction threshold."""
    op.alter_column(
        "agent_config",
        "max_total_tokens",
        existing_type=sa.Integer(),
        server_default=sa.text("100000"),
        existing_nullable=False,
    )
    op.alter_column(
        "agent_config",
        "compaction_threshold_tokens",
        existing_type=sa.Integer(),
        server_default=sa.text("75000"),
        existing_nullable=False,
    )
    op.execute("UPDATE agent_config SET max_total_tokens = 100000 WHERE max_total_tokens = 64000")
    op.execute(
        "UPDATE agent_config SET compaction_threshold_tokens = 75000 "
        "WHERE compaction_threshold_tokens = 48000"
    )


def downgrade() -> None:
    """Restore the previous budget defaults."""
    op.execute(
        "UPDATE agent_config SET compaction_threshold_tokens = 48000 "
        "WHERE compaction_threshold_tokens = 75000"
    )
    op.execute("UPDATE agent_config SET max_total_tokens = 64000 WHERE max_total_tokens = 100000")
    op.alter_column(
        "agent_config",
        "max_total_tokens",
        existing_type=sa.Integer(),
        server_default=sa.text("64000"),
        existing_nullable=False,
    )
    op.alter_column(
        "agent_config",
        "compaction_threshold_tokens",
        existing_type=sa.Integer(),
        server_default=sa.text("48000"),
        existing_nullable=False,
    )
