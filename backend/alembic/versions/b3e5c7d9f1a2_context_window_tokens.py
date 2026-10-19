"""agent config model context window

Revision ID: b3e5c7d9f1a2
Revises: d4b8e6f1a2c7
Create Date: 2026-10-19 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3e5c7d9f1a2"
down_revision: str | None = "d4b8e6f1a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_config",
        sa.Column(
            "context_window_tokens",
            sa.Integer(),
            server_default=sa.text("1000000"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_agent_config_context_window_tokens_range"),
        "agent_config",
        "context_window_tokens BETWEEN 8000 AND 2000000",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_agent_config_context_window_tokens_range"),
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "context_window_tokens")
