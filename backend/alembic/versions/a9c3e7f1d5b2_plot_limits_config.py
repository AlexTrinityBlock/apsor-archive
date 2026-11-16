"""configurable render_plot budgets

Revision ID: a9c3e7f1d5b2
Revises: c1a4e7b9d2f3
Create Date: 2026-11-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9c3e7f1d5b2"
down_revision: str | None = "c1a4e7b9d2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_config",
        sa.Column(
            "max_plot_points",
            sa.Integer(),
            server_default=sa.text("10000"),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "max_plot_bytes",
            sa.Integer(),
            server_default=sa.text("600000"),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "max_plot_nodes",
            sa.Integer(),
            server_default=sa.text("100000"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_agent_config_max_plot_points_range",
        "agent_config",
        "max_plot_points BETWEEN 100 AND 50000",
    )
    op.create_check_constraint(
        "ck_agent_config_max_plot_bytes_range",
        "agent_config",
        "max_plot_bytes BETWEEN 10000 AND 2000000",
    )
    op.create_check_constraint(
        "ck_agent_config_max_plot_nodes_range",
        "agent_config",
        "max_plot_nodes BETWEEN 1000 AND 500000",
    )
    op.create_check_constraint(
        "ck_agent_config_plot_nodes_at_least_points",
        "agent_config",
        "max_plot_nodes >= max_plot_points",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_config_plot_nodes_at_least_points",
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_config_max_plot_nodes_range",
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_config_max_plot_bytes_range",
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_config_max_plot_points_range",
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "max_plot_nodes")
    op.drop_column("agent_config", "max_plot_bytes")
    op.drop_column("agent_config", "max_plot_points")
