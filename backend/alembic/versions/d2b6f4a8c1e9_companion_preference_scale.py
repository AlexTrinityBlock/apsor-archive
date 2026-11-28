"""companion preference: continuous display scale

Revision ID: d2b6f4a8c1e9
Revises: c5f1a8d3e7b4
Create Date: 2026-11-28 18:00:00.000000

Adds ``companion_preference.scale``, a nullable float from 0 (compact) to 1
(full) set by direct on-screen resizing. NULL means "use the ``size`` preset",
so existing rows need no backfill. The table's owner-only RLS policy and
``apsor_app`` grants are unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2b6f4a8c1e9"
down_revision: str | None = "c5f1a8d3e7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companion_preference", sa.Column("scale", sa.Float(), nullable=True))
    op.create_check_constraint(
        op.f("ck_companion_preference_scale_range"),
        "companion_preference",
        "scale IS NULL OR (scale >= 0 AND scale <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_companion_preference_scale_range"),
        "companion_preference",
        type_="check",
    )
    op.drop_column("companion_preference", "scale")
