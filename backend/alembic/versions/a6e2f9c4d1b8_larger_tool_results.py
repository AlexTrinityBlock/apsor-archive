"""raise the per-result tool character cap

Revision ID: a6e2f9c4d1b8
Revises: f3c8d5a1b7e2
Create Date: 2026-10-19 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6e2f9c4d1b8"
down_revision: str | None = "f3c8d5a1b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Raise the default and migrate the untouched default row."""
    op.alter_column(
        "agent_config",
        "max_tool_result_chars",
        existing_type=sa.Integer(),
        server_default=sa.text("100000"),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE agent_config SET max_tool_result_chars = 100000 "
        "WHERE max_tool_result_chars < 100000"
    )


def downgrade() -> None:
    """Restore the previous default and the matching value."""
    op.execute(
        "UPDATE agent_config SET max_tool_result_chars = 12000 "
        "WHERE max_tool_result_chars = 100000"
    )
    op.alter_column(
        "agent_config",
        "max_tool_result_chars",
        existing_type=sa.Integer(),
        server_default=sa.text("12000"),
        existing_nullable=False,
    )
