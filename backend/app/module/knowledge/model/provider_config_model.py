"""Four physical provider tables sharing one Python column mixin.

The user explicitly chose one table per capability.  ``ProviderConfigMixin``
only shares the Python column definitions; it never creates a fifth table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow


class ProviderConfigMixin:
    """Columns shared by every provider capability table.

    SQLAlchemy copies these ``mapped_column`` declarations into every concrete
    subclass; the mixin itself is not a declarative class, so no fifth table is
    created.
    """

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
        server_default=text("''"),
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )


def _provider_table_args(
    *,
    table_name: str,
    provider_check: str,
    model_check: str,
    model_constraint: str,
    dimension_check: str,
) -> tuple[Any, ...]:
    """Build the identical constraint/index set for one capability table.

    Constraint names use the short suffix because ``Base.metadata`` applies the
    ``ck_<table>_<name>`` naming convention.  Chat and web tables share this
    helper, but their model checks differ (required vs. NULL), so the constraint
    suffix is explicit and must match the Alembic migration.  The partial unique
    index is the only source of truth for "at most one active row per
    capability"; there is intentionally no separate ``enabled`` column or
    active-pointer table.

    ``Any`` is used for the return type because SQLAlchemy's table-argument
    tuple mixes ``CheckConstraint`` and ``Index`` instances.
    """
    return (
        CheckConstraint(provider_check, name="provider_valid"),
        CheckConstraint(model_check, name=model_constraint),
        CheckConstraint(dimension_check, name="dimension_null"),
        CheckConstraint("char_length(label) <= 80", name="label_length"),
        Index(
            f"uq_{table_name}_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


def _embedding_table_args() -> tuple[Any, ...]:
    """Embedding uses a dimension range check instead of a NULL check."""
    return (
        CheckConstraint(
            "provider IN ('hashing', 'openai', 'openai-compatible', 'none')",
            name="provider_valid",
        ),
        CheckConstraint(
            "char_length(model) BETWEEN 1 AND 128",
            name="model_required",
        ),
        CheckConstraint(
            "dimension IS NULL OR dimension BETWEEN 16 AND 4096",
            name="dimension_range",
        ),
        CheckConstraint("char_length(label) <= 80", name="label_length"),
        Index(
            "uq_embedding_provider_config_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class ChatProviderConfigModel(Base, ProviderConfigMixin):
    """Saved chat/LLM provider configurations."""

    __tablename__ = "chat_provider_config"
    __table_args__ = _provider_table_args(
        table_name="chat_provider_config",
        provider_check="provider IN ('deepseek', 'openai-compatible', 'none')",
        model_check="char_length(model) BETWEEN 1 AND 128",
        model_constraint="model_required",
        dimension_check="dimension IS NULL",
    )


class EmbeddingProviderConfigModel(Base, ProviderConfigMixin):
    """Saved embedding provider configurations."""

    __tablename__ = "embedding_provider_config"
    __table_args__ = _embedding_table_args()


class WebSearchProviderConfigModel(Base, ProviderConfigMixin):
    """Saved web-search provider configurations."""

    __tablename__ = "web_search_provider_config"
    __table_args__ = _provider_table_args(
        table_name="web_search_provider_config",
        provider_check="provider IN ('tavily', 'none')",
        model_check="model IS NULL",
        model_constraint="model_null",
        dimension_check="dimension IS NULL",
    )


class WebFetchProviderConfigModel(Base, ProviderConfigMixin):
    """Saved web-fetch provider configurations."""

    __tablename__ = "web_fetch_provider_config"
    __table_args__ = _provider_table_args(
        table_name="web_fetch_provider_config",
        provider_check="provider IN ('tavily', 'none')",
        model_check="model IS NULL",
        model_constraint="model_null",
        dimension_check="dimension IS NULL",
    )


PROVIDER_CONFIG_MODELS: tuple[type[ProviderConfigMixin], ...] = (
    ChatProviderConfigModel,
    EmbeddingProviderConfigModel,
    WebSearchProviderConfigModel,
    WebFetchProviderConfigModel,
)

__all__ = [
    "PROVIDER_CONFIG_MODELS",
    "ChatProviderConfigModel",
    "EmbeddingProviderConfigModel",
    "ProviderConfigMixin",
    "WebFetchProviderConfigModel",
    "WebSearchProviderConfigModel",
]
