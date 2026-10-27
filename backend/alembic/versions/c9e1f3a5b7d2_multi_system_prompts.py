"""multi-section system prompts

Revision ID: c9e1f3a5b7d2
Revises: b8d2e4f6a1c3
Create Date: 2026-10-25 12:00:00.000000

Migration decisions:
- Create the new table first, copy the old singleton, and only then drop the old
  table. If any step fails, the old data is still fully preserved, so the
  deployment can be retried safely.
- If the body of the old ``system_prompt`` is blank only (or there is no row), no
  new section is created. This matches the old service semantics where a blank
  body meant "not enabled".
- A title that is blank only falls back to ``System prompt`` because the new
  table requires a title of at least 1 character. That fallback only happens in
  the migration; afterwards the service rejects blank titles with 422.
- Downgrade copies the section with the smallest ``sort_order, id`` back into the
  singleton. Several sections cannot be downgraded losslessly into a single row,
  so the first one is chosen and the expected behavior is stated in the
  message; the old table is rebuilt before the new one is dropped so content is
  not lost if the downgrade fails.
- The old ORM model is not imported; everything uses raw SQL so the migration is
  not tied to future model changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9e1f3a5b7d2"
down_revision: str | None = "b8d2e4f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_prompt_section",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200",
            name=op.f("ck_system_prompt_section_title_length"),
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 32000",
            name=op.f("ck_system_prompt_section_body_length"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name=op.f("ck_system_prompt_section_sort_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_prompt_section")),
    )
    op.create_index(
        "ix_system_prompt_section_order",
        "system_prompt_section",
        ["sort_order", "id"],
        unique=False,
    )

    # The old singleton had exactly one row (id = 1) and no created_at. Using
    # updated_at as both created_at and updated_at on the new row keeps the
    # creation time shown in Settings from moving backwards. sort_order is fixed
    # at 10, leaving gaps for future manual inserts.
    op.execute(
        sa.text(
            """
            INSERT INTO system_prompt_section
                (title, body, sort_order, created_at, updated_at)
            SELECT
                COALESCE(NULLIF(btrim(title), ''), 'System prompt'),
                body,
                10,
                updated_at,
                updated_at
            FROM system_prompt
            WHERE char_length(btrim(body)) > 0
            """
        )
    )

    op.drop_table("system_prompt")


def downgrade() -> None:
    # Rebuild the old singleton schema first; the id = 1 check constraint is
    # exactly the same as in the original migration, so the previous application
    # version starts cleanly after a downgrade.
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

    # The many-to-one downgrade keeps only the first section; if there is no
    # section at all, the old table stays without rows, matching the previous
    # "no custom prompt after a reset" state.
    op.execute(
        sa.text(
            """
            INSERT INTO system_prompt (id, title, body, updated_at)
            SELECT 1, title, body, updated_at
            FROM system_prompt_section
            ORDER BY sort_order, id
            LIMIT 1
            """
        )
    )

    op.drop_index("ix_system_prompt_section_order", table_name="system_prompt_section")
    op.drop_table("system_prompt_section")
