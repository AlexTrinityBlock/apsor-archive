"""memory titles, direct deprecation, editable built-in prompt

Revision ID: f4a1c7d9e2b3
Revises: c9e1f3a5b7d2
Create Date: 2026-10-25 18:00:00.000000

Migration decisions:
- ``memory.title`` is added as nullable, backfilled from the first 80 characters
  of the content, and only then set to NOT NULL. Existing rows therefore never
  block the upgrade just because no AI provider is configured.
- Existing deprecated rows get ``deprecated_at`` backfilled from ``updated_at``
  because the old data only records the fact that a row was superseded, not a
  more precise retirement time. A new direct deprecation always writes
  ``deprecated_at`` in the same UPDATE.
- The old ``deprecated_has_successor`` constraint required every deprecated row
  to have a successor; the new constraint accepts either a successor or
  ``deprecated_at`` as provenance.
- The downgrade re-adds the old constraint with ``NOT VALID``: existing directly
  deprecated rows have no successor, so forcing validation would make the
  downgrade fail. The previous code still only ever produced deprecated rows
  with a successor, so new writes are unaffected.
- ``system_prompt_section.builtin_key`` only stores the four built-in overrides;
  NULL means a user-defined section. The partial unique index allows at most one
  row per built-in, and deleting that row restores the Python default, so the
  migration does not need to copy a whole default prompt.
- ``app_user.display_name`` and ``bio`` are an optional owner profile; NULL means
  unset and the UI falls back to the username. They only affect the
  ``owner_profile`` section of new conversations and never rewrite the prompt
  already frozen into an existing conversation.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4a1c7d9e2b3"
down_revision: str | None = "c9e1f3a5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Memory title (nullable -> backfill -> NOT NULL).
    # ------------------------------------------------------------------
    op.add_column("memory", sa.Column("title", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE memory
            SET title = COALESCE(
                NULLIF(
                    left(
                        regexp_replace(btrim(content), '[[:space:]]+', ' ', 'g'),
                        80
                    ),
                    ''
                ),
                'Untitled memory'
            )
            WHERE title IS NULL
            """
        )
    )
    op.alter_column(
        "memory",
        "title",
        existing_type=sa.Text(),
        type_=sa.String(length=120),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_memory_title_length"),
        "memory",
        "char_length(title) BETWEEN 1 AND 120",
    )

    # ------------------------------------------------------------------
    # 2. Direct deprecation provenance.
    # ------------------------------------------------------------------
    op.add_column(
        "memory",
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory",
        sa.Column("deprecated_reason", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE memory
            SET deprecated_at = updated_at
            WHERE status = 'deprecated' AND deprecated_at IS NULL
            """
        )
    )
    op.drop_constraint(
        op.f("ck_memory_deprecated_has_successor"),
        "memory",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_memory_deprecated_has_provenance"),
        "memory",
        "status = 'active' OR superseded_by_id IS NOT NULL OR deprecated_at IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_memory_deprecated_reason_length"),
        "memory",
        "deprecated_reason IS NULL OR char_length(deprecated_reason) <= 500",
    )

    # ------------------------------------------------------------------
    # 3. Editable built-in system prompt overrides.
    # ------------------------------------------------------------------
    op.add_column(
        "system_prompt_section",
        sa.Column("builtin_key", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_system_prompt_section_builtin_key_valid"),
        "system_prompt_section",
        "builtin_key IS NULL OR builtin_key IN "
        "('identity', 'instructions', 'examples', 'context_protocol')",
    )
    op.create_index(
        "uq_system_prompt_section_builtin_key",
        "system_prompt_section",
        ["builtin_key"],
        unique=True,
        postgresql_where=sa.text("builtin_key IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # 4. Owner profile (display name + self-introduction).
    # ------------------------------------------------------------------
    op.add_column(
        "app_user",
        sa.Column("display_name", sa.String(length=80), nullable=True),
    )
    op.add_column("app_user", sa.Column("bio", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_app_user_display_name_length"),
        "app_user",
        "display_name IS NULL OR char_length(display_name) BETWEEN 1 AND 80",
    )
    op.create_check_constraint(
        op.f("ck_app_user_bio_length"),
        "app_user",
        "bio IS NULL OR char_length(bio) <= 2000",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_app_user_bio_length"),
        "app_user",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_app_user_display_name_length"),
        "app_user",
        type_="check",
    )
    op.drop_column("app_user", "bio")
    op.drop_column("app_user", "display_name")

    op.drop_index(
        "uq_system_prompt_section_builtin_key",
        table_name="system_prompt_section",
    )
    op.drop_constraint(
        op.f("ck_system_prompt_section_builtin_key_valid"),
        "system_prompt_section",
        type_="check",
    )
    op.drop_column("system_prompt_section", "builtin_key")

    op.drop_constraint(
        op.f("ck_memory_deprecated_reason_length"),
        "memory",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_memory_deprecated_has_provenance"),
        "memory",
        type_="check",
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE memory
            ADD CONSTRAINT ck_memory_deprecated_has_successor
            CHECK (status = 'active' OR superseded_by_id IS NOT NULL)
            NOT VALID
            """
        )
    )
    op.drop_column("memory", "deprecated_reason")
    op.drop_column("memory", "deprecated_at")

    op.drop_constraint(
        op.f("ck_memory_title_length"),
        "memory",
        type_="check",
    )
    op.drop_column("memory", "title")
