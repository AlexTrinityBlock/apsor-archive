"""chat upload client token

Revision ID: b7e2d9f4a1c6
Revises: d2f6b8a0c4e1
Create Date: 2026-11-11 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2d9f4a1c6"
down_revision: str | None = "d2f6b8a0c4e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_chat_attachment",
        sa.Column("client_token", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_agent_chat_attachment_user_client_token"),
        "agent_chat_attachment",
        ["user_id", "client_token"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_agent_chat_attachment_user_client_token"),
        "agent_chat_attachment",
        type_="unique",
    )
    op.drop_column("agent_chat_attachment", "client_token")
