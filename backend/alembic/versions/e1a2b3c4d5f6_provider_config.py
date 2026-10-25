"""split ai_provider_config into four capability provider tables

Revision ID: e1a2b3c4d5f6
Revises: d5e9f3a7b2c1
Create Date: 2026-10-25 04:10:00.000000

舊版只有一個 ``ai_provider_config``，以 ``purpose`` 區分 chat/embedding。
本版改成四張實體表（使用者最終決策 C），並把舊資料分別搬到 chat 與
embedding 表。Web search / web fetch 是全新 capability，沒有舊資料。

此檔刻意不 import 已刪除的 ``AiProviderConfigModel``；所有舊表操作都用
``sa.table()`` / raw SQL，避免 Alembic 依賴目前應用程式的 ORM 模型。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a2b3c4d5f6"
down_revision: str | None = "d5e9f3a7b2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_provider_table(
    *,
    table_name: str,
    provider_check: str,
    model_check: str,
    model_constraint: str,
    dimension_check: str,
    dimension_constraint: str,
    model_nullable: bool,
) -> None:
    """建立一張 capability 表；四張表欄位相同，只有 constraint 不同。"""
    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "label",
            sa.String(length=80),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=model_nullable),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("api_key_hint", sa.String(length=16), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
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
        sa.CheckConstraint(provider_check, name=op.f(f"ck_{table_name}_provider_valid")),
        sa.CheckConstraint(model_check, name=op.f(f"ck_{table_name}_{model_constraint}")),
        sa.CheckConstraint(
            dimension_check,
            name=op.f(f"ck_{table_name}_{dimension_constraint}"),
        ),
        sa.CheckConstraint(
            "char_length(label) <= 80",
            name=op.f(f"ck_{table_name}_label_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
    )
    # Partial unique index：每個 capability 最多一列 is_active=true。
    # is_active 是唯一 active 狀態來源，不另設 enabled 欄位或 pointer 表。
    op.create_index(
        f"uq_{table_name}_active",
        table_name,
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def upgrade() -> None:
    _create_provider_table(
        table_name="chat_provider_config",
        provider_check="provider IN ('deepseek', 'openai-compatible', 'none')",
        model_check="char_length(model) BETWEEN 1 AND 128",
        dimension_check="dimension IS NULL",
        model_constraint="model_required",
        dimension_constraint="dimension_null",
        model_nullable=False,
    )
    _create_provider_table(
        table_name="embedding_provider_config",
        provider_check="provider IN ('hashing', 'openai', 'openai-compatible', 'none')",
        model_check="char_length(model) BETWEEN 1 AND 128",
        dimension_check="dimension IS NULL OR dimension BETWEEN 16 AND 4096",
        model_constraint="model_required",
        dimension_constraint="dimension_range",
        model_nullable=False,
    )
    _create_provider_table(
        table_name="web_search_provider_config",
        provider_check="provider IN ('tavily', 'none')",
        model_check="model IS NULL",
        dimension_check="dimension IS NULL",
        model_constraint="model_null",
        dimension_constraint="dimension_null",
        model_nullable=True,
    )
    _create_provider_table(
        table_name="web_fetch_provider_config",
        provider_check="provider IN ('tavily', 'none')",
        model_check="model IS NULL",
        dimension_check="dimension IS NULL",
        model_constraint="model_null",
        dimension_constraint="dimension_null",
        model_nullable=True,
    )

    # 舊資料搬遷：id 不複製，讓新表的 identity 從 1 開始遞增；不重設 sequence。
    # label 舊表沒有，依 plan 填入 provider 名稱。
    op.execute(
        sa.text(
            """
            INSERT INTO chat_provider_config (
                provider, label, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, is_active, created_at, updated_at
            )
            SELECT
                provider, provider, model, base_url, api_key_ciphertext,
                api_key_hint, NULL, enabled, created_at, updated_at
            FROM ai_provider_config
            WHERE purpose = 'chat'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO embedding_provider_config (
                provider, label, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, is_active, created_at, updated_at
            )
            SELECT
                provider, provider, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, enabled, created_at, updated_at
            FROM ai_provider_config
            WHERE purpose = 'embedding'
            """
        )
    )
    op.drop_table("ai_provider_config")


def downgrade() -> None:
    # 舊表沿用原本 schema 與 uq_ai_provider_config_purpose。
    op.create_table(
        "ai_provider_config",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("api_key_hint", sa.String(length=16), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('chat', 'embedding')",
            name=op.f("ck_ai_provider_config_purpose_valid"),
        ),
        sa.CheckConstraint(
            "dimension IS NULL OR (dimension >= 16 AND dimension <= 4096)",
            name=op.f("ck_ai_provider_config_dimension_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_provider_config")),
        sa.UniqueConstraint("purpose", name="uq_ai_provider_config_purpose"),
    )

    # 每個 capability 取 active 的一列；若沒有 active，取 id 最小的一列。
    # 這樣 downgrade 後仍保留使用者最近啟用的設定。
    op.execute(
        sa.text(
            """
            INSERT INTO ai_provider_config (
                purpose, provider, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, enabled, created_at, updated_at
            )
            SELECT
                'chat', provider, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, is_active, created_at, updated_at
            FROM chat_provider_config
            ORDER BY is_active DESC, id ASC
            LIMIT 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO ai_provider_config (
                purpose, provider, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, enabled, created_at, updated_at
            )
            SELECT
                'embedding', provider, model, base_url, api_key_ciphertext,
                api_key_hint, dimension, is_active, created_at, updated_at
            FROM embedding_provider_config
            ORDER BY is_active DESC, id ASC
            LIMIT 1
            """
        )
    )

    op.drop_table("web_fetch_provider_config")
    op.drop_table("web_search_provider_config")
    op.drop_table("embedding_provider_config")
    op.drop_table("chat_provider_config")
