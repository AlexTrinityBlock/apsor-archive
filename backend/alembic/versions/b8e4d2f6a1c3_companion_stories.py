"""companion stories: persona and lore overrides plus the companion bond

Revision ID: b8e4d2f6a1c3
Revises: a7d3c9e1f5b2
Create Date: 2026-11-28 12:00:00.000000

Three private tables, each with ``user_id``, a forced owner-only RLS policy,
and the four DML grants for ``apsor_app``:

- ``companion_story``: one account's copy-on-write story for one companion in
  one locale. Exactly one of ``preset_id`` / ``companion_id`` is set; a custom
  companion's story cascades through ``(companion_id, user_id)``.
- ``companion_lore_fragment``: the fragments of a customized story, cascading
  through ``(story_id, user_id)``.
- ``companion_bond``: completed runs per companion reference, which unlock
  lore tiers, plus when each tier opened.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8e4d2f6a1c3"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
OWNER_CHECK = "user_id = nullif(current_setting('app.user_id', true), '')::bigint"


def _secure(table: str, sequence: str | None) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    if sequence is not None:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {APP_ROLE} "
        f"USING ({OWNER_CHECK}) WITH CHECK ({OWNER_CHECK})"
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "companion_story",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("preset_id", sa.String(length=48), nullable=True),
        sa.Column("companion_id", sa.BigInteger(), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column(
            "lore_customized",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "(preset_id IS NULL) <> (companion_id IS NULL)",
            name=op.f("ck_companion_story_one_target"),
        ),
        sa.CheckConstraint(
            "locale IN ('en', 'zh-TW', 'zh-CN')",
            name=op.f("ck_companion_story_locale_valid"),
        ),
        sa.CheckConstraint(
            "persona IS NULL OR char_length(persona) BETWEEN 1 AND 4000",
            name=op.f("ck_companion_story_persona_length"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_story_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["companion_id", "user_id"],
            ["companion.id", "companion.user_id"],
            name="fk_companion_story_companion_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_story")),
        sa.UniqueConstraint("id", "user_id", name="uq_companion_story_id_user_id"),
    )
    op.create_index(
        "uq_companion_story_preset",
        "companion_story",
        ["user_id", "preset_id", "locale"],
        unique=True,
        postgresql_where=sa.text("preset_id IS NOT NULL"),
    )
    op.create_index(
        "uq_companion_story_custom",
        "companion_story",
        ["user_id", "companion_id", "locale"],
        unique=True,
        postgresql_where=sa.text("companion_id IS NOT NULL"),
    )

    op.create_table(
        "companion_lore_fragment",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("story_id", sa.BigInteger(), nullable=False),
        sa.Column("fragment_key", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "themes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "edited",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "tier IN ('first', 'familiar', 'rare')",
            name=op.f("ck_companion_lore_fragment_tier_valid"),
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 2000",
            name=op.f("ck_companion_lore_fragment_text_length"),
        ),
        sa.CheckConstraint(
            "fragment_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'",
            name=op.f("ck_companion_lore_fragment_fragment_key_format"),
        ),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_companion_lore_fragment_position_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_lore_fragment_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["story_id", "user_id"],
            ["companion_story.id", "companion_story.user_id"],
            name="fk_companion_lore_fragment_story_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_lore_fragment")),
        sa.UniqueConstraint(
            "story_id",
            "fragment_key",
            name="uq_companion_lore_fragment_key",
        ),
    )
    op.create_index(
        "ix_companion_lore_fragment_story",
        "companion_lore_fragment",
        ["user_id", "story_id", "position"],
        unique=False,
    )

    op.create_table(
        "companion_bond",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column(
            "completed_runs",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("familiar_unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rare_unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "completed_runs >= 0",
            name=op.f("ck_companion_bond_runs_non_negative"),
        ),
        sa.CheckConstraint(
            "char_length(companion_ref) BETWEEN 1 AND 64",
            name=op.f("ck_companion_bond_companion_ref_length"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_bond_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", "companion_ref", name=op.f("pk_companion_bond")),
    )

    _secure("companion_story", "companion_story_id_seq")
    _secure("companion_lore_fragment", "companion_lore_fragment_id_seq")
    _secure("companion_bond", None)


def downgrade() -> None:
    op.drop_table("companion_bond")
    op.drop_index("ix_companion_lore_fragment_story", table_name="companion_lore_fragment")
    op.drop_table("companion_lore_fragment")
    op.drop_index("uq_companion_story_custom", table_name="companion_story")
    op.drop_index("uq_companion_story_preset", table_name="companion_story")
    op.drop_table("companion_story")
