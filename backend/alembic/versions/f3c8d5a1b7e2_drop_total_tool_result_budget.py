"""drop turn-wide tool-result budget

Revision ID: f3c8d5a1b7e2
Revises: e7a1c4b9d2f6
Create Date: 2026-10-19 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3c8d5a1b7e2"
down_revision: str | None = "e7a1c4b9d2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep only the per-result cap; no turn-wide starvation."""
    op.drop_constraint(
        op.f("ck_agent_config_tool_result_within_total"),
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_config_max_total_tool_result_chars_range"),
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "max_total_tool_result_chars")


def downgrade() -> None:
    """Restore the legacy total cap for older deployments."""
    op.add_column(
        "agent_config",
        sa.Column(
            "max_total_tool_result_chars",
            sa.Integer(),
            server_default=sa.text("24000"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_agent_config_max_total_tool_result_chars_range"),
        "agent_config",
        "max_total_tool_result_chars BETWEEN 1000 AND 200000",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_tool_result_within_total"),
        "agent_config",
        "max_tool_result_chars <= max_total_tool_result_chars",
    )
