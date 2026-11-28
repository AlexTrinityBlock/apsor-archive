"""Make the auxiliary reasoning effort optional.

Revision ID: a3e7c1f9d2b4
Revises: f2c8d4a6b9e1
Create Date: 2026-11-28

The auxiliary slot used to default to ``reasoning_effort = 'low'``. Models
without reasoning support (for example ``gpt-4.1-mini`` on an OpenAI-compatible
endpoint) reject that parameter, so an assignment could fail its probe without
the user ever choosing an effort. NULL now means "omit the field". Existing
values are kept as they are; the provider client drops a rejected effort.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3e7c1f9d2b4"
down_revision: str | None = "f2c8d4a6b9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "ck_app_user_aux_effort_length"


def upgrade() -> None:
    """Allow NULL, drop the 'low' server default, and relax the length check."""
    op.drop_constraint(op.f(_CHECK), "app_user", type_="check")
    op.alter_column(
        "app_user",
        "aux_reasoning_effort",
        existing_type=sa.String(length=32),
        nullable=True,
        server_default=None,
    )
    op.create_check_constraint(
        op.f(_CHECK),
        "app_user",
        "aux_reasoning_effort IS NULL OR char_length(aux_reasoning_effort) BETWEEN 1 AND 32",
    )


def downgrade() -> None:
    """Restore the NOT NULL column with the 'low' default."""
    op.drop_constraint(op.f(_CHECK), "app_user", type_="check")
    op.execute("UPDATE app_user SET aux_reasoning_effort = 'low' WHERE aux_reasoning_effort IS NULL")
    op.alter_column(
        "app_user",
        "aux_reasoning_effort",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'low'"),
    )
    op.create_check_constraint(
        op.f(_CHECK),
        "app_user",
        "char_length(aux_reasoning_effort) BETWEEN 1 AND 32",
    )
