"""drop the agent turn caps

Revision ID: d8f2a6c4e1b9
Revises: a4c9e2f7b1d6
Create Date: 2026-11-25 10:00:00.000000

Migration decisions:
- A tool-heavy turn could exhaust the 20-call or 24-step guards while the model
  still had useful reads to make. The run then failed with ``tool_call_limit``
  or ``step_limit`` and the transcript showed an unfinished-run notice.
- The loop now continues until the model answers or a real failure stops it
  (provider error, usage quota, or user cancellation). The concurrency bound
  ``max_parallel_tools`` remains; only the cumulative turn caps are removed.
- Downgrade restores both columns and their checks. The restored call cap is
  raised to at least ``max_parallel_tools`` so an existing row cannot violate
  the ``parallel_within_tool_calls`` check.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8f2a6c4e1b9"
down_revision: str | None = "a4c9e2f7b1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_MAX_STEPS = 24
DEFAULT_MAX_TOOL_CALLS = 20


def upgrade() -> None:
    """Remove the cumulative step and tool-call caps."""
    op.drop_constraint(
        op.f("ck_agent_config_parallel_within_tool_calls"),
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_config_max_tool_calls_per_turn_range"),
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_config_max_steps_range"),
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "max_tool_calls_per_turn")
    op.drop_column("agent_config", "max_steps")


def downgrade() -> None:
    """Restore the legacy cumulative caps for older deployments."""
    op.add_column(
        "agent_config",
        sa.Column(
            "max_steps",
            sa.Integer(),
            server_default=sa.text(str(DEFAULT_MAX_STEPS)),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "max_tool_calls_per_turn",
            sa.Integer(),
            server_default=sa.text(str(DEFAULT_MAX_TOOL_CALLS)),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE agent_config "
        f"SET max_tool_calls_per_turn = GREATEST(max_parallel_tools, {DEFAULT_MAX_TOOL_CALLS})"
    )
    op.create_check_constraint(
        op.f("ck_agent_config_max_steps_range"),
        "agent_config",
        "max_steps BETWEEN 1 AND 32",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_max_tool_calls_per_turn_range"),
        "agent_config",
        "max_tool_calls_per_turn BETWEEN 1 AND 24",
    )
    op.create_check_constraint(
        op.f("ck_agent_config_parallel_within_tool_calls"),
        "agent_config",
        "max_parallel_tools <= max_tool_calls_per_turn",
    )
