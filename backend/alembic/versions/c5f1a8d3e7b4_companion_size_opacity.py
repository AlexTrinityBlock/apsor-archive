"""companion preference: display size and opacity mode

Revision ID: c5f1a8d3e7b4
Revises: b8e4d2f6a1c3
Create Date: 2026-11-28 14:00:00.000000

Adds two per-account display settings to ``companion_preference``. Both columns
have server defaults, so existing rows keep working without a backfill; the
table's owner-only RLS policy and ``apsor_app`` grants are unchanged.

- ``size``: ``compact``, ``medium``, or ``full`` (default ``full``).
- ``opacity_mode``: ``opaque``, ``translucent``, or ``auto`` (default ``opaque``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5f1a8d3e7b4"
down_revision: str | None = "b8e4d2f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companion_preference",
        sa.Column("size", sa.String(length=16), server_default=sa.text("'full'"), nullable=False),
    )
    op.add_column(
        "companion_preference",
        sa.Column(
            "opacity_mode",
            sa.String(length=16),
            server_default=sa.text("'opaque'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_companion_preference_size_valid"),
        "companion_preference",
        "size IN ('compact', 'medium', 'full')",
    )
    op.create_check_constraint(
        op.f("ck_companion_preference_opacity_mode_valid"),
        "companion_preference",
        "opacity_mode IN ('opaque', 'translucent', 'auto')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_companion_preference_opacity_mode_valid"),
        "companion_preference",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_companion_preference_size_valid"),
        "companion_preference",
        type_="check",
    )
    op.drop_column("companion_preference", "opacity_mode")
    op.drop_column("companion_preference", "size")
