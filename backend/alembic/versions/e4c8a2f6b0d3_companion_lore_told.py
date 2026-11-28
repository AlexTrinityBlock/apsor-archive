"""companion lore told: story pacing per account and companion

Revision ID: e4c8a2f6b0d3
Revises: d2b6f4a8c1e9
Create Date: 2026-11-28 18:00:00.000000

- ``companion_bond.last_story_run``: the completed-run count when the last
  story moment was offered, so moments come every few runs.
- ``companion_lore_told``: per-account lore progress: which fragments were
  offered, how often (``told_count``), first and last time (``offered_at``,
  ``last_told_at``), and the latest path (``source``). Private: ``user_id``, a forced owner-only RLS policy, and the four
  DML grants for ``apsor_app``. No sequence.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4c8a2f6b0d3"
down_revision: str | None = "d2b6f4a8c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
OWNER_CHECK = "user_id = nullif(current_setting('app.user_id', true), '')::bigint"


def upgrade() -> None:
    op.add_column("companion_bond", sa.Column("last_story_run", sa.Integer(), nullable=True))
    op.create_table(
        "companion_lore_told",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column("fragment_key", sa.String(length=64), nullable=False),
        sa.Column("told_count", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "offered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_told_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "told_count >= 1",
            name=op.f("ck_companion_lore_told_told_count_positive"),
        ),
        sa.CheckConstraint(
            "char_length(companion_ref) BETWEEN 1 AND 64",
            name=op.f("ck_companion_lore_told_companion_ref_length"),
        ),
        sa.CheckConstraint(
            "fragment_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'",
            name=op.f("ck_companion_lore_told_fragment_key_format"),
        ),
        sa.CheckConstraint(
            "source IN ('topical', 'story_moment', 'self_query')",
            name=op.f("ck_companion_lore_told_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_lore_told_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "companion_ref",
            "fragment_key",
            name=op.f("pk_companion_lore_told"),
        ),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON companion_lore_told TO {APP_ROLE}")
    op.execute("ALTER TABLE companion_lore_told ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companion_lore_told FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY companion_lore_told_owner ON companion_lore_told FOR ALL TO {APP_ROLE} "
        f"USING ({OWNER_CHECK}) WITH CHECK ({OWNER_CHECK})"
    )


def downgrade() -> None:
    op.drop_table("companion_lore_told")
    op.drop_column("companion_bond", "last_story_run")
