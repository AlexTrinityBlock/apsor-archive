"""add the singleton custom system prompt

Revision ID: d5e9f3a7b2c1
Revises: c4d8e2f6a1b9
Create Date: 2026-10-25 02:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e9f3a7b2c1"
down_revision: str | None = "c4d8e2f6a1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_prompt",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_system_prompt_singleton")),
        sa.CheckConstraint(
            "char_length(title) <= 200",
            name=op.f("ck_system_prompt_title_length"),
        ),
        sa.CheckConstraint(
            "char_length(body) <= 32000",
            name=op.f("ck_system_prompt_body_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_prompt")),
    )


def downgrade() -> None:
    op.drop_table("system_prompt")
