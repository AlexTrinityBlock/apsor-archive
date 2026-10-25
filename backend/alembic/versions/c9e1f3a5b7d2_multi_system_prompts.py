"""multi-section system prompts

Revision ID: c9e1f3a5b7d2
Revises: b8d2e4f6a1c3
Create Date: 2026-10-25 12:00:00.000000

Migration 決策：
- 先建新表、再複製舊 singleton、最後才 drop 舊表。任何一步失敗時舊資料仍
  完整保留，部署可以安全重跑。
- 舊 ``system_prompt`` 的 body 若只有空白（或沒有列），不建立新 section；
  這與舊 service「空白 body 視為未啟用」的語意一致。
- 標題只有空白時回退成 ``System prompt``，因為新表要求 title 長度至少 1；
  這個回退只發生在遷移，之後的空白標題由 service 以 422 拒絕。
- Downgrade 取 ``sort_order, id`` 最小的 section 複製回 singleton。多條
  section 無法無損降級成單一列，因此選擇第一條並在訊息中保留可預期的行為；
  舊表重建後才 drop 新表，避免降級失敗時遺失內容。
- 不 import 舊 ORM model，全部使用 raw SQL，避免 migration 與未來 model
  變動互相綁死。
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

    # 舊 singleton 只有一列（id=1），且沒有 created_at。把 updated_at 同時
    # 當成新列的 created_at/updated_at，讓 Settings 顯示的建立時間不會倒退。
    # sort_order 固定 10，為未來手動插入留出空隙。
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
    # 先重建舊 singleton schema；id=1 的 check constraint 與原 migration 完全
    # 相同，確保 downgrade 後舊版程式可以無縫啟動。
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

    # 多對一降級只保留第一條 section；若沒有任何 section，舊表保持沒有列，
    # 對應舊版「reset 後沒有 custom prompt」的狀態。
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
