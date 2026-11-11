"""database-backed temporary chat image lifetime

Revision ID: d2f6b8a0c4e1
Revises: b4e6d8f0a2c5
Create Date: 2026-11-11 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2f6b8a0c4e1"
down_revision: str | None = "b4e6d8f0a2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_config",
        sa.Column(
            "chat_attachment_staged_ttl_hours",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_config",
        sa.Column(
            "chat_attachment_cleanup_interval_seconds",
            sa.Integer(),
            server_default=sa.text("900"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_agent_config_chat_attachment_staged_ttl_range",
        "agent_config",
        "chat_attachment_staged_ttl_hours BETWEEN 1 AND 168",
    )
    op.create_check_constraint(
        "ck_agent_config_chat_attachment_cleanup_interval_range",
        "agent_config",
        "chat_attachment_cleanup_interval_seconds BETWEEN 60 AND 86400",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_config_chat_attachment_cleanup_interval_range",
        "agent_config",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_config_chat_attachment_staged_ttl_range",
        "agent_config",
        type_="check",
    )
    op.drop_column("agent_config", "chat_attachment_cleanup_interval_seconds")
    op.drop_column("agent_config", "chat_attachment_staged_ttl_hours")
