"""user profile cards

Revision ID: b7e2d4f6a8c1
Revises: f4a1c7d9e2b3
Create Date: 2026-10-25 20:00:00.000000

Migration 決策：
- 使用者描述從單一 ``app_user.bio`` 改成有序的 ``user_profile_card``，
  每張卡有 title/content，讓同一個使用者可以分成 Work、Interests、
  Answer preferences 等多個區塊。
- 升級時先建立新表，再把既有 bio 複製成第一張 ``About`` 卡，最後才 drop
  ``app_user.bio``。任何一步失敗時舊資料仍完整保留。
- Downgrade 把第一張卡（``sort_order, id``）複製回 ``bio``，然後 drop 新表。
  多張卡無法無損降級成單一欄位，因此只保留第一張；這與舊版單一自我介紹的
  語意一致。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2d4f6a8c1"
down_revision: str | None = "f4a1c7d9e2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profile_card",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
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
            "char_length(title) BETWEEN 1 AND 120",
            name=op.f("ck_user_profile_card_title_length"),
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 2000",
            name=op.f("ck_user_profile_card_content_length"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name=op.f("ck_user_profile_card_sort_order"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_profile_card_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_profile_card")),
    )
    op.create_index(
        "ix_user_profile_card_order",
        "user_profile_card",
        ["user_id", "sort_order", "id"],
        unique=False,
    )

    # The old single bio becomes the first card. Empty/whitespace-only bios do
    # not create a row, matching the old "no bio set" state.
    op.execute(
        sa.text(
            """
            INSERT INTO user_profile_card
                (user_id, title, content, sort_order, created_at, updated_at)
            SELECT id, 'About', btrim(bio), 10, now(), now()
            FROM app_user
            WHERE bio IS NOT NULL AND btrim(bio) <> ''
            """
        )
    )

    op.drop_constraint(
        op.f("ck_app_user_bio_length"),
        "app_user",
        type_="check",
    )
    op.drop_column("app_user", "bio")


def downgrade() -> None:
    op.add_column("app_user", sa.Column("bio", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE app_user AS users
            SET bio = cards.content
            FROM (
                SELECT DISTINCT ON (user_id) user_id, content
                FROM user_profile_card
                ORDER BY user_id, sort_order, id
            ) AS cards
            WHERE cards.user_id = users.id
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_app_user_bio_length"),
        "app_user",
        "bio IS NULL OR char_length(bio) <= 2000",
    )

    op.drop_index("ix_user_profile_card_order", table_name="user_profile_card")
    op.drop_table("user_profile_card")
