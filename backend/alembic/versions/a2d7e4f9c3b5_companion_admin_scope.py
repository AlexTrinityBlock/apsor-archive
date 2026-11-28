"""companion admin scope: root white-box over companion rows, account policy

Revision ID: a2d7e4f9c3b5
Revises: f1a6c3e8b2d4
Create Date: 2026-11-28 20:10:00.000000

Root administers companions per account (an explicit, documented exception to
"root is not a data superuser" that covers companion tables only, never the
archive). The exception is a database policy that applies only when a root
transaction also carries ``app.admin_scope = 'companion'``:

- ``{table}_companion_admin`` (FOR ALL) on ``companion_story``,
  ``companion_lore_fragment``, ``companion_bond``, ``companion_lore_told``.
- ``companion_companion_admin_read`` (SELECT) on ``companion``, so root can show
  custom companion names; ``companion_frame`` (user artwork) stays owner-only.
- New admin-managed tables the user can read but never write
  (``{table}_owner_read`` + ``{table}_companion_admin``):
  ``companion_account_policy``, ``companion_user_config``,
  ``companion_admin_story_override``, ``companion_admin_lore_override``.
- ``companion_admin_access_log``: append-only audit (SELECT and INSERT grants
  only) of root reading or changing a user's companion story.

Also: bond conversation counters for life stories, ``refs`` on account lore
fragments, and the ``admin`` told source.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a2d7e4f9c3b5"
down_revision: str | None = "f1a6c3e8b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
OWNER_CHECK = "user_id = nullif(current_setting('app.user_id', true), '')::bigint"
ADMIN_CHECK = (
    "current_setting('app.user_role', true) = 'root' "
    "AND current_setting('app.admin_scope', true) = 'companion'"
)
LOCALES = "'en', 'zh-TW', 'zh-CN'"
TIERS = "'first', 'familiar', 'rare'"
KEY_FORMAT = "'^[a-z0-9][a-z0-9-]{0,63}$'"

ADMIN_VISIBLE = (
    "companion_story",
    "companion_lore_fragment",
    "companion_bond",
    "companion_lore_told",
)
ADMIN_MANAGED = (
    "companion_account_policy",
    "companion_user_config",
    "companion_admin_story_override",
    "companion_admin_lore_override",
)


def _user_fk(table: str, column: str = "user_id") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        ["app_user.id"],
        name=op.f(f"fk_{table}_{column}_app_user"),
        ondelete="RESTRICT",
    )


def _timestamps() -> list[sa.Column]:
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


def _jsonb(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=None if nullable else sa.text("'[]'::jsonb"),
        nullable=nullable,
    )


def upgrade() -> None:
    # --- bond, lore fragment, told ---------------------------------------
    op.add_column(
        "companion_bond",
        sa.Column("conversations", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "companion_bond",
        sa.Column("last_conversation_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "companion_bond",
        sa.Column(
            "last_life_story_conversations",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "companion_bond",
        sa.Column("admin_adjusted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_companion_bond_conversations_non_negative"),
        "companion_bond",
        "conversations >= 0 AND last_life_story_conversations >= 0",
    )
    op.add_column(
        "companion_lore_fragment",
        sa.Column(
            "refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        "source IN ('topical', 'story_moment', 'self_query', 'admin')",
    )

    # --- admin-managed tables ---------------------------------------------
    op.create_table(
        "companion_account_policy",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("default_ref", sa.String(length=64), nullable=True),
        _jsonb("allowed_refs", nullable=True),
        sa.Column("allow_custom", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("pinned_ref", sa.String(length=64), nullable=True),
        sa.Column("pin_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        _user_fk("companion_account_policy"),
        sa.CheckConstraint(
            "pin_enabled = false OR pinned_ref IS NOT NULL",
            name=op.f("ck_companion_account_policy_pin_has_ref"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_companion_account_policy")),
    )

    op.create_table(
        "companion_user_config",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("familiar_unlock_runs", sa.Integer(), nullable=True),
        sa.Column("rare_unlock_runs", sa.Integer(), nullable=True),
        sa.Column("max_recalled_fragments", sa.Integer(), nullable=True),
        sa.Column("topical_min_similarity", sa.Float(), nullable=True),
        sa.Column("untold_bonus", sa.Float(), nullable=True),
        sa.Column("told_penalty", sa.Float(), nullable=True),
        sa.Column("told_penalty_cap", sa.Integer(), nullable=True),
        sa.Column("story_moment_every_runs", sa.Integer(), nullable=True),
        sa.Column("self_query_window", sa.Integer(), nullable=True),
        sa.Column("max_contributions_per_run", sa.Integer(), nullable=True),
        sa.Column("life_story_enabled", sa.Boolean(), nullable=True),
        sa.Column("life_story_every_conversations", sa.Integer(), nullable=True),
        sa.Column("life_story_tier", sa.String(length=16), nullable=True),
        sa.Column("life_story_max_per_30d", sa.Integer(), nullable=True),
        sa.Column("life_story_require_review", sa.Boolean(), nullable=True),
        *_timestamps(),
        _user_fk("companion_user_config"),
        sa.CheckConstraint(
            "familiar_unlock_runs IS NULL OR familiar_unlock_runs BETWEEN 0 AND 1000",
            name=op.f("ck_companion_user_config_familiar_unlock_runs_range"),
        ),
        sa.CheckConstraint(
            "rare_unlock_runs IS NULL OR rare_unlock_runs BETWEEN 0 AND 10000",
            name=op.f("ck_companion_user_config_rare_unlock_runs_range"),
        ),
        sa.CheckConstraint(
            "max_recalled_fragments IS NULL OR max_recalled_fragments BETWEEN 0 AND 5",
            name=op.f("ck_companion_user_config_max_recalled_fragments_range"),
        ),
        sa.CheckConstraint(
            "topical_min_similarity IS NULL OR topical_min_similarity BETWEEN 0 AND 1",
            name=op.f("ck_companion_user_config_topical_min_similarity_range"),
        ),
        sa.CheckConstraint(
            "untold_bonus IS NULL OR untold_bonus BETWEEN 0 AND 1",
            name=op.f("ck_companion_user_config_untold_bonus_range"),
        ),
        sa.CheckConstraint(
            "told_penalty IS NULL OR told_penalty BETWEEN 0 AND 1",
            name=op.f("ck_companion_user_config_told_penalty_range"),
        ),
        sa.CheckConstraint(
            "told_penalty_cap IS NULL OR told_penalty_cap BETWEEN 0 AND 20",
            name=op.f("ck_companion_user_config_told_penalty_cap_range"),
        ),
        sa.CheckConstraint(
            "story_moment_every_runs IS NULL OR story_moment_every_runs BETWEEN 0 AND 100",
            name=op.f("ck_companion_user_config_story_moment_every_runs_range"),
        ),
        sa.CheckConstraint(
            "self_query_window IS NULL OR self_query_window BETWEEN 1 AND 50",
            name=op.f("ck_companion_user_config_self_query_window_range"),
        ),
        sa.CheckConstraint(
            "max_contributions_per_run IS NULL OR max_contributions_per_run BETWEEN 0 AND 5",
            name=op.f("ck_companion_user_config_max_contributions_per_run_range"),
        ),
        sa.CheckConstraint(
            "life_story_every_conversations IS NULL "
            "OR life_story_every_conversations BETWEEN 3 AND 1000",
            name=op.f("ck_companion_user_config_life_story_every_conversations_range"),
        ),
        sa.CheckConstraint(
            f"life_story_tier IS NULL OR life_story_tier IN ({TIERS})",
            name=op.f("ck_companion_user_config_life_story_tier_valid"),
        ),
        sa.CheckConstraint(
            "life_story_max_per_30d IS NULL OR life_story_max_per_30d BETWEEN 0 AND 60",
            name=op.f("ck_companion_user_config_life_story_max_per_30d_range"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_companion_user_config")),
    )

    op.create_table(
        "companion_admin_story_override",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("persona", sa.Text(), nullable=False),
        *_timestamps(),
        _user_fk("companion_admin_story_override"),
        sa.CheckConstraint(
            f"locale IN ({LOCALES})",
            name=op.f("ck_companion_admin_story_override_locale_valid"),
        ),
        sa.CheckConstraint(
            "char_length(persona) BETWEEN 1 AND 4000",
            name=op.f("ck_companion_admin_story_override_persona_length"),
        ),
        sa.CheckConstraint(
            "char_length(companion_ref) BETWEEN 1 AND 64",
            name=op.f("ck_companion_admin_story_override_companion_ref_length"),
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "companion_ref",
            "locale",
            name=op.f("pk_companion_admin_story_override"),
        ),
    )

    op.create_table(
        "companion_admin_lore_override",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("fragment_key", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=True),
        _jsonb("themes"),
        _jsonb("refs"),
        sa.Column("position", sa.Integer(), nullable=True),
        *_timestamps(),
        _user_fk("companion_admin_lore_override"),
        sa.CheckConstraint(
            f"locale IN ({LOCALES})",
            name=op.f("ck_companion_admin_lore_override_locale_valid"),
        ),
        sa.CheckConstraint(
            "action IN ('replace', 'add', 'hide')",
            name=op.f("ck_companion_admin_lore_override_action_valid"),
        ),
        sa.CheckConstraint(
            "action = 'hide' OR (text IS NOT NULL AND char_length(text) BETWEEN 1 AND 2000)",
            name=op.f("ck_companion_admin_lore_override_text_present"),
        ),
        sa.CheckConstraint(
            f"tier IS NULL OR tier IN ({TIERS})",
            name=op.f("ck_companion_admin_lore_override_tier_valid"),
        ),
        sa.CheckConstraint(
            f"fragment_key ~ {KEY_FORMAT}",
            name=op.f("ck_companion_admin_lore_override_fragment_key_format"),
        ),
        sa.CheckConstraint(
            "position IS NULL OR position >= 0",
            name=op.f("ck_companion_admin_lore_override_position_non_negative"),
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "companion_ref",
            "locale",
            "fragment_key",
            name=op.f("pk_companion_admin_lore_override"),
        ),
    )

    op.create_table(
        "companion_admin_access_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("story_id", sa.BigInteger(), nullable=True),
        sa.Column("companion_ref", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _user_fk("companion_admin_access_log", "actor_user_id"),
        _user_fk("companion_admin_access_log", "target_user_id"),
        sa.CheckConstraint(
            "action IN ('view_full_text', 'edit', 'regenerate', 'delete', 'generate', "
            "'override', 'reset_progress', 'adjust_progress')",
            name=op.f("ck_companion_admin_access_log_action_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_admin_access_log")),
    )
    op.create_index(
        "ix_companion_admin_access_log_target",
        "companion_admin_access_log",
        ["target_user_id", "at"],
    )

    # --- policies -------------------------------------------------------------
    for table in ADMIN_VISIBLE:
        op.execute(
            f"CREATE POLICY {table}_companion_admin ON {table} FOR ALL TO {APP_ROLE} "
            f"USING ({ADMIN_CHECK}) WITH CHECK ({ADMIN_CHECK})"
        )
    op.execute(
        f"CREATE POLICY companion_companion_admin_read ON companion FOR SELECT TO {APP_ROLE} "
        f"USING ({ADMIN_CHECK})"
    )
    for table in ADMIN_MANAGED:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner_read ON {table} FOR SELECT TO {APP_ROLE} "
            f"USING ({OWNER_CHECK})"
        )
        op.execute(
            f"CREATE POLICY {table}_companion_admin ON {table} FOR ALL TO {APP_ROLE} "
            f"USING ({ADMIN_CHECK}) WITH CHECK ({ADMIN_CHECK})"
        )
    audit = "companion_admin_access_log"
    op.execute(f"GRANT SELECT, INSERT ON {audit} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {audit}_id_seq TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {audit} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {audit} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {audit}_root_read ON {audit} FOR SELECT TO {APP_ROLE} USING ({ADMIN_CHECK})"
    )
    op.execute(
        f"CREATE POLICY {audit}_root_insert ON {audit} FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({ADMIN_CHECK})"
    )


def downgrade() -> None:
    op.drop_table("companion_admin_access_log")
    for table in reversed(ADMIN_MANAGED):
        op.drop_table(table)
    op.execute("DROP POLICY IF EXISTS companion_companion_admin_read ON companion")
    for table in ADMIN_VISIBLE:
        op.execute(f"DROP POLICY IF EXISTS {table}_companion_admin ON {table}")
    op.execute("DELETE FROM companion_lore_told WHERE source = 'admin'")
    op.drop_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_companion_lore_told_source_valid"),
        "companion_lore_told",
        "source IN ('topical', 'story_moment', 'self_query')",
    )
    op.drop_column("companion_lore_fragment", "refs")
    op.drop_constraint(
        op.f("ck_companion_bond_conversations_non_negative"),
        "companion_bond",
        type_="check",
    )
    op.drop_column("companion_bond", "admin_adjusted_at")
    op.drop_column("companion_bond", "last_life_story_conversations")
    op.drop_column("companion_bond", "last_conversation_id")
    op.drop_column("companion_bond", "conversations")
