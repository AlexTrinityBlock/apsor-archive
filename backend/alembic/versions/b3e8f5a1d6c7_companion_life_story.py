"""companion life story: generated stories and their durable jobs

Revision ID: b3e8f5a1d6c7
Revises: a2d7e4f9c3b5
Create Date: 2026-11-28 20:20:00.000000

Every few conversations the dedicated worker writes a short "life story": the
librarians' world opens an illusory door into the user's own life, built from
the user's own memories with the account's own model. The story is saved as a
generated lore item for that user and companion and may surface later like any
other memory.

- ``companion_generated_story``: the story text (bounded), its title, tier,
  themes, status (draft | published | retired), and provenance
  (``source_refs`` holds memory/file ids and counts only, never content).
- ``companion_story_job``: the durable job ledger (queued → running →
  succeeded | skipped | failed | cancelled), idempotent per ``trigger_key``.

Both are private (``{table}_owner``) and root-visible under the companion
admin scope (``{table}_companion_admin``).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3e8f5a1d6c7"
down_revision: str | None = "a2d7e4f9c3b5"
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
TABLES = ("companion_story_job", "companion_generated_story")


def upgrade() -> None:
    op.create_table(
        "companion_story_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("trigger_key", sa.String(length=128), nullable=False),
        sa.Column("replaces_story_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "not_before",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_story_job_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"locale IN ({LOCALES})",
            name=op.f("ck_companion_story_job_locale_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('cadence', 'admin', 'regenerate')",
            name=op.f("ck_companion_story_job_trigger_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'skipped', 'failed', "
            "'cancel_requested', 'cancelled')",
            name=op.f("ck_companion_story_job_status_valid"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_companion_story_job_attempts_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_story_job")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_companion_story_job_id_user_id")),
        sa.UniqueConstraint(
            "user_id",
            "trigger_key",
            name=op.f("uq_companion_story_job_user_id_trigger_key"),
        ),
    )
    op.create_index(
        "ix_companion_story_job_active",
        "companion_story_job",
        ["status", "not_before"],
        postgresql_where=sa.text("status IN ('queued', 'running', 'cancel_requested')"),
    )

    op.create_table(
        "companion_generated_story",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("companion_ref", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("fragment_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column(
            "themes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'published'"),
            nullable=False,
        ),
        sa.Column(
            "source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("job_id", sa.BigInteger(), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("provider_config_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("admin_edited_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_companion_generated_story_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "user_id"],
            ["companion_story_job.id", "companion_story_job.user_id"],
            name=op.f("fk_companion_generated_story_job_user"),
            ondelete="SET NULL (job_id)",
        ),
        sa.CheckConstraint(
            f"locale IN ({LOCALES})",
            name=op.f("ck_companion_generated_story_locale_valid"),
        ),
        sa.CheckConstraint(
            f"tier IN ({TIERS})",
            name=op.f("ck_companion_generated_story_tier_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name=op.f("ck_companion_generated_story_status_valid"),
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 4000",
            name=op.f("ck_companion_generated_story_text_length"),
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120",
            name=op.f("ck_companion_generated_story_title_length"),
        ),
        sa.CheckConstraint(
            "fragment_key ~ '^g-[a-z0-9-]{1,62}$'",
            name=op.f("ck_companion_generated_story_fragment_key_format"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companion_generated_story")),
        sa.UniqueConstraint(
            "user_id",
            "job_id",
            name=op.f("uq_companion_generated_story_user_id_job_id"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "companion_ref",
            "fragment_key",
            name=op.f("uq_companion_generated_story_user_id_ref_key"),
        ),
    )
    op.create_index(
        "ix_companion_generated_story_user_ref",
        "companion_generated_story",
        ["user_id", "companion_ref", "status", "created_at"],
    )

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {APP_ROLE} "
            f"USING ({OWNER_CHECK}) WITH CHECK ({OWNER_CHECK})"
        )
        op.execute(
            f"CREATE POLICY {table}_companion_admin ON {table} FOR ALL TO {APP_ROLE} "
            f"USING ({ADMIN_CHECK}) WITH CHECK ({ADMIN_CHECK})"
        )


def downgrade() -> None:
    op.drop_table("companion_generated_story")
    op.drop_table("companion_story_job")
