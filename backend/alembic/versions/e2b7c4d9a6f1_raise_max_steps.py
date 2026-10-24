"""raise the default agent step allowance

Revision ID: e2b7c4d9a6f1
Revises: b7d2e9c4a1f6
Create Date: 2026-10-19 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2b7c4d9a6f1"
down_revision: str | None = "b7d2e9c4a1f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Raise the step guard for difficult, tool-heavy turns."""
    op.alter_column(
        "agent_config",
        "max_steps",
        existing_type=sa.Integer(),
        server_default=sa.text("24"),
        existing_nullable=False,
    )
    op.execute("UPDATE agent_config SET max_steps = 24 WHERE max_steps = 8")


def downgrade() -> None:
    """Restore the previous step guard."""
    op.execute("UPDATE agent_config SET max_steps = 8 WHERE max_steps = 24")
    op.alter_column(
        "agent_config",
        "max_steps",
        existing_type=sa.Integer(),
        server_default=sa.text("8"),
        existing_nullable=False,
    )
