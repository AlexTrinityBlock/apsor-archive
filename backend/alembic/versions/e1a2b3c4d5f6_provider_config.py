"""split ai_provider_config into four capability provider tables

Revision ID: e1a2b3c4d5f6
Revises: d5e9f3a7b2c1
Create Date: 2026-10-25 04:10:00.000000

The previous version had a single ``ai_provider_config`` table that used
``purpose`` to distinguish chat from embedding. This version replaces it with
four physical tables (the user's final decision, option C) and moves the old rows
into the chat and embedding tables respectively. Web search and web fetch are
entirely new capabilities with no legacy data.

This file deliberately does not import the deleted ``AiProviderConfigModel``;
every operation on the old table uses ``sa.table()`` / raw SQL so Alembic does
not depend on the application's current ORM models.
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
    """Create one capability table; all four share the columns, only the constraints differ."""
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
    # Partial unique index: at most one row per capability has is_active = true.
    # is_active is the only source of active state; there is no separate enabled
    # column or pointer table.
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

    # Legacy data migration: ids are not copied, so the new tables' identity
    # columns start at 1; the sequence is not reset. The old table had no label,
    # so the provider name is used as the label per the plan.
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
    # The old table keeps its original schema and uq_ai_provider_config_purpose.
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

    # Take the active row for each capability; if none is active, take the row
    # with the smallest id. That way the downgrade still keeps the settings the
    # user enabled most recently.
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
