"""memory titles, direct deprecation, editable built-in prompt

Revision ID: f4a1c7d9e2b3
Revises: c9e1f3a5b7d2
Create Date: 2026-10-25 18:00:00.000000

Migration 決策：
- ``memory.title`` 先以 nullable 加入，再用內容前 80 字元回填，最後才設
  NOT NULL。既有列不會因為沒有 AI provider 而卡住升級。
- 既有 deprecated 列以 ``updated_at`` 回填 ``deprecated_at``，因為舊資料
  只有「已被取代」這個事實，沒有更精確的退役時間。新的直接作廢一定會在
  同一筆 UPDATE 寫入 ``deprecated_at``。
- 舊 constraint ``deprecated_has_successor`` 要求 deprecated 必須有 successor；
  新 constraint 允許 successor 或 ``deprecated_at`` 其中一種 provenance。
- downgrade 重加舊 constraint 時使用 ``NOT VALID``：直接作廢的既有列沒有
  successor，若強制 validate 會讓降級失敗。舊版程式仍然只會產生有 successor
  的 deprecated 列，所以新寫入不受影響。
- ``system_prompt_section.builtin_key`` 只存放四個 built-in override；NULL
  代表使用者自訂 section。Partial unique index 讓每個 built-in 最多一列，
  刪除該列即回覆 Python 預設值，不需要在 migration 複製整段預設 prompt。
- ``app_user.display_name`` 與 ``bio`` 是可選的 owner profile；NULL 代表尚未
  設定，UI 會回退到 username。它們只影響新對話的 ``owner_profile`` section，
  不會改寫既有對話已凍結的 prompt。
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
