"""save memory approval toggle

Revision ID: c8f2a4b6d9e1
Revises: b3e5c7d9f1a2
Create Date: 2026-10-19 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8f2a4b6d9e1"
down_revision: str | None = "b3e5c7d9f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_config",
        sa.Column(
            "save_memory_requires_approval",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_config", "save_memory_requires_approval")
