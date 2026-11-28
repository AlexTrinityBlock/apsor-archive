"""companion world content: database-backed presets, lore, canon, docs, config

Revision ID: f1a6c3e8b2d4
Revises: e4c8a2f6b0d3
Create Date: 2026-11-28 20:00:00.000000

Companion stories stop living only in files. The files under
``app/module/companion/lore`` become seed data; these global tables hold the
live, root-editable copy:

- ``companion_preset`` / ``companion_preset_text``: the six preset librarians,
  their order, the global default, and the localized name and persona.
- ``companion_lore_item`` / ``companion_lore_item_text``: preset lore
  fragments (tier, themes, canon refs) and their localized text.
- ``companion_canon_entity``: localized canon entity names and summaries.
- ``companion_world_doc`` / ``companion_world_doc_revision``: the world bible,
  glossary, character bibles, and term tables, with a short revision history.
- ``companion_config``: the singleton of every story tunable (cadence,
  thresholds, word lists, life-story schedule and budgets).
- ``companion_prompt_template``: every guidance string and prompt template.
- ``companion_seed_state``: which seed bundle has been applied, so startup
  seeding is idempotent and never overwrites admin edits.

Seeded rows carry ``seed_hash`` (the shipped text they came from),
``upstream_seed_hash`` (set when a newer shipped text arrives for a row root
has edited), and ``admin_modified``. All tables are global configuration:
read-all, root-write, forced RLS, four DML grants for ``apsor_app``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f1a6c3e8b2d4"
down_revision: str | None = "e4c8a2f6b0d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
LOCALES = "'en', 'zh-TW', 'zh-CN'"
TIERS = "'first', 'familiar', 'rare'"
KEY_FORMAT = "'^[a-z0-9][a-z0-9-]{0,63}$'"
ROOT = "current_setting('app.user_role', true) = 'root'"

TABLES = (
    "companion_preset",
    "companion_preset_text",
    "companion_lore_item",
    "companion_lore_item_text",
    "companion_canon_entity",
    "companion_world_doc",
    "companion_world_doc_revision",
    "companion_config",
    "companion_prompt_template",
    "companion_seed_state",
)
SEQUENCES = (
    "companion_lore_item_id_seq",
    "companion_world_doc_revision_id_seq",
)


def _seed_columns(table: str) -> list[sa.Column]:
    """Return the provenance columns every seeded, root-editable row carries."""
    return [
        sa.Column("seed_hash", sa.String(length=64), nullable=True),
        sa.Column("upstream_seed_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "admin_modified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "app_user.id",
                ondelete="SET NULL",
                name=op.f(f"fk_{table}_updated_by_user_id_app_user"),
            ),
            nullable=True,
        ),
    ]


def _jsonb_list(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "companion_preset",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "is_global_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        *_seed_columns("companion_preset"),
        sa.CheckConstraint(f"id ~ {KEY_FORMAT}", name=op.f("ck_companion_preset_id_format")),
        sa.CheckConstraint("position >= 0", name=op.f("ck_companion_preset_position_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_preset")),
    )
    op.create_index(
        "uq_companion_preset_global_default",
        "companion_preset",
        ["is_global_default"],
        unique=True,
        postgresql_where=sa.text("is_global_default"),
    )

    op.create_table(
        "companion_preset_text",
        sa.Column("preset_id", sa.String(length=48), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("persona", sa.Text(), nullable=False),
        *_seed_columns("companion_preset_text"),
        sa.CheckConstraint(f"locale IN ({LOCALES})", name=op.f("ck_companion_preset_text_locale_valid")),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 40",
            name=op.f("ck_companion_preset_text_name_length"),
        ),
        sa.CheckConstraint(
            "char_length(persona) BETWEEN 1 AND 4000",
            name=op.f("ck_companion_preset_text_persona_length"),
        ),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["companion_preset.id"],
            name=op.f("fk_companion_preset_text_preset_id_companion_preset"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("preset_id", "locale", name=op.f("pk_companion_preset_text")),
    )

    op.create_table(
        "companion_lore_item",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("preset_id", sa.String(length=48), nullable=False),
        sa.Column("fragment_key", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        _jsonb_list("themes"),
        _jsonb_list("refs"),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        *_seed_columns("companion_lore_item"),
        sa.CheckConstraint(f"tier IN ({TIERS})", name=op.f("ck_companion_lore_item_tier_valid")),
        sa.CheckConstraint(
            f"fragment_key ~ {KEY_FORMAT}",
            name=op.f("ck_companion_lore_item_fragment_key_format"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_companion_lore_item_position_non_negative")),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["companion_preset.id"],
            name=op.f("fk_companion_lore_item_preset_id_companion_preset"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_lore_item")),
        sa.UniqueConstraint(
            "preset_id",
            "fragment_key",
            name=op.f("uq_companion_lore_item_preset_id_fragment_key"),
        ),
    )
    op.create_index(
        "ix_companion_lore_item_preset_position",
        "companion_lore_item",
        ["preset_id", "position"],
    )

    op.create_table(
        "companion_lore_item_text",
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        *_seed_columns("companion_lore_item_text"),
        sa.CheckConstraint(f"locale IN ({LOCALES})", name=op.f("ck_companion_lore_item_text_locale_valid")),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 2000",
            name=op.f("ck_companion_lore_item_text_text_length"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["companion_lore_item.id"],
            name=op.f("fk_companion_lore_item_text_item_id_companion_lore_item"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", "locale", name=op.f("pk_companion_lore_item_text")),
    )

    op.create_table(
        "companion_canon_entity",
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        *_seed_columns("companion_canon_entity"),
        sa.CheckConstraint(f"locale IN ({LOCALES})", name=op.f("ck_companion_canon_entity_locale_valid")),
        sa.CheckConstraint(
            f"entity_id ~ {KEY_FORMAT}",
            name=op.f("ck_companion_canon_entity_entity_id_format"),
        ),
        sa.CheckConstraint(
            "char_length(summary) <= 1000",
            name=op.f("ck_companion_canon_entity_summary_length"),
        ),
        sa.PrimaryKeyConstraint("entity_id", "locale", name=op.f("pk_companion_canon_entity")),
    )

    op.create_table(
        "companion_world_doc",
        sa.Column("doc_key", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_seed_columns("companion_world_doc"),
        sa.CheckConstraint(f"locale IN ({LOCALES})", name=op.f("ck_companion_world_doc_locale_valid")),
        sa.CheckConstraint(
            "kind IN ('bible', 'glossary', 'world', 'terms', 'character')",
            name=op.f("ck_companion_world_doc_kind_valid"),
        ),
        sa.CheckConstraint(
            "doc_key ~ '^[a-z0-9][a-z0-9:-]{0,63}$'",
            name=op.f("ck_companion_world_doc_doc_key_format"),
        ),
        sa.CheckConstraint(
            "char_length(body_md) <= 200000",
            name=op.f("ck_companion_world_doc_body_length"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_companion_world_doc_version_positive")),
        sa.PrimaryKeyConstraint("doc_key", "locale", name=op.f("pk_companion_world_doc")),
    )

    op.create_table(
        "companion_world_doc_revision",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_key", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "app_user.id",
                ondelete="SET NULL",
                name=op.f("fk_companion_world_doc_revision_created_by_user_id_app_user"),
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["doc_key", "locale"],
            ["companion_world_doc.doc_key", "companion_world_doc.locale"],
            name=op.f("fk_companion_world_doc_revision_doc_companion_world_doc"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_world_doc_revision")),
    )
    op.create_index(
        "ix_companion_world_doc_revision_doc",
        "companion_world_doc_revision",
        ["doc_key", "locale", "version"],
    )

    op.create_table(
        "companion_config",
        sa.Column("id", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("familiar_unlock_runs", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("rare_unlock_runs", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("max_recalled_fragments", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column(
            "topical_min_similarity",
            sa.Float(),
            server_default=sa.text("0.30"),
            nullable=False,
        ),
        sa.Column("untold_bonus", sa.Float(), server_default=sa.text("0.06"), nullable=False),
        sa.Column("told_penalty", sa.Float(), server_default=sa.text("0.04"), nullable=False),
        sa.Column("told_penalty_cap", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column(
            "story_moment_every_runs",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("self_query_window", sa.Integer(), server_default=sa.text("6"), nullable=False),
        sa.Column(
            "max_contributions_per_run",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
        _jsonb_list("self_query_phrases"),
        _jsonb_list("self_canon_terms"),
        _jsonb_list("banned_address_terms"),
        sa.Column("life_story_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "life_story_every_conversations",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "life_story_tier",
            sa.String(length=16),
            server_default=sa.text("'familiar'"),
            nullable=False,
        ),
        sa.Column("life_story_max_per_30d", sa.Integer(), server_default=sa.text("4"), nullable=False),
        sa.Column("life_story_memory_limit", sa.Integer(), server_default=sa.text("8"), nullable=False),
        sa.Column(
            "life_story_memory_chars",
            sa.Integer(),
            server_default=sa.text("6000"),
            nullable=False,
        ),
        sa.Column(
            "life_story_canon_chars",
            sa.Integer(),
            server_default=sa.text("4000"),
            nullable=False,
        ),
        sa.Column(
            "life_story_max_output_tokens",
            sa.Integer(),
            server_default=sa.text("1500"),
            nullable=False,
        ),
        sa.Column("life_story_max_chars", sa.Integer(), server_default=sa.text("2400"), nullable=False),
        sa.Column(
            "life_story_require_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "life_story_poll_seconds",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column("life_story_max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_seed_columns("companion_config"),
        sa.CheckConstraint("id = 1", name=op.f("ck_companion_config_singleton")),
        sa.CheckConstraint(
            "familiar_unlock_runs BETWEEN 0 AND 1000",
            name=op.f("ck_companion_config_familiar_unlock_runs_range"),
        ),
        sa.CheckConstraint(
            "rare_unlock_runs BETWEEN 0 AND 10000 AND rare_unlock_runs >= familiar_unlock_runs",
            name=op.f("ck_companion_config_rare_unlock_runs_range"),
        ),
        sa.CheckConstraint(
            "max_recalled_fragments BETWEEN 0 AND 5",
            name=op.f("ck_companion_config_max_recalled_fragments_range"),
        ),
        sa.CheckConstraint(
            "topical_min_similarity BETWEEN 0 AND 1",
            name=op.f("ck_companion_config_topical_min_similarity_range"),
        ),
        sa.CheckConstraint(
            "untold_bonus BETWEEN 0 AND 1",
            name=op.f("ck_companion_config_untold_bonus_range"),
        ),
        sa.CheckConstraint(
            "told_penalty BETWEEN 0 AND 1",
            name=op.f("ck_companion_config_told_penalty_range"),
        ),
        sa.CheckConstraint(
            "told_penalty_cap BETWEEN 0 AND 20",
            name=op.f("ck_companion_config_told_penalty_cap_range"),
        ),
        sa.CheckConstraint(
            "story_moment_every_runs BETWEEN 0 AND 100",
            name=op.f("ck_companion_config_story_moment_every_runs_range"),
        ),
        sa.CheckConstraint(
            "self_query_window BETWEEN 1 AND 50",
            name=op.f("ck_companion_config_self_query_window_range"),
        ),
        sa.CheckConstraint(
            "max_contributions_per_run BETWEEN 0 AND 5",
            name=op.f("ck_companion_config_max_contributions_per_run_range"),
        ),
        sa.CheckConstraint(
            "life_story_every_conversations BETWEEN 3 AND 1000",
            name=op.f("ck_companion_config_life_story_every_conversations_range"),
        ),
        sa.CheckConstraint(
            f"life_story_tier IN ({TIERS})",
            name=op.f("ck_companion_config_life_story_tier_valid"),
        ),
        sa.CheckConstraint(
            "life_story_max_per_30d BETWEEN 0 AND 60",
            name=op.f("ck_companion_config_life_story_max_per_30d_range"),
        ),
        sa.CheckConstraint(
            "life_story_memory_limit BETWEEN 1 AND 40",
            name=op.f("ck_companion_config_life_story_memory_limit_range"),
        ),
        sa.CheckConstraint(
            "life_story_memory_chars BETWEEN 500 AND 20000",
            name=op.f("ck_companion_config_life_story_memory_chars_range"),
        ),
        sa.CheckConstraint(
            "life_story_canon_chars BETWEEN 500 AND 20000",
            name=op.f("ck_companion_config_life_story_canon_chars_range"),
        ),
        sa.CheckConstraint(
            "life_story_max_output_tokens BETWEEN 200 AND 8000",
            name=op.f("ck_companion_config_life_story_max_output_tokens_range"),
        ),
        sa.CheckConstraint(
            "life_story_max_chars BETWEEN 400 AND 4000",
            name=op.f("ck_companion_config_life_story_max_chars_range"),
        ),
        sa.CheckConstraint(
            "life_story_poll_seconds BETWEEN 5 AND 3600",
            name=op.f("ck_companion_config_life_story_poll_seconds_range"),
        ),
        sa.CheckConstraint(
            "life_story_max_attempts BETWEEN 1 AND 10",
            name=op.f("ck_companion_config_life_story_max_attempts_range"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_companion_config_version_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_config")),
    )

    op.create_table(
        "companion_prompt_template",
        sa.Column("template_key", sa.String(length=48), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _jsonb_list("required_placeholders"),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_seed_columns("companion_prompt_template"),
        sa.CheckConstraint(
            f"locale IN ({LOCALES})",
            name=op.f("ck_companion_prompt_template_locale_valid"),
        ),
        sa.CheckConstraint(
            "template_key ~ '^[a-z][a-z0-9_]{0,47}$'",
            name=op.f("ck_companion_prompt_template_key_format"),
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 20000",
            name=op.f("ck_companion_prompt_template_body_length"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_companion_prompt_template_version_positive"),
        ),
        sa.PrimaryKeyConstraint(
            "template_key",
            "locale",
            name=op.f("pk_companion_prompt_template"),
        ),
    )

    op.create_table(
        "companion_seed_state",
        sa.Column("bundle", sa.String(length=48), nullable=False),
        sa.Column("seed_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "content_version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("bundle", name=op.f("pk_companion_seed_state")),
    )

    # The singleton exists from the start; the seeder fills the word lists.
    op.execute("INSERT INTO companion_config (id) VALUES (1)")

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT TO {APP_ROLE} USING (true)")
        op.execute(
            f"CREATE POLICY {table}_root_write ON {table} FOR ALL TO {APP_ROLE} "
            f"USING ({ROOT}) WITH CHECK ({ROOT})"
        )
    for sequence in SEQUENCES:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
