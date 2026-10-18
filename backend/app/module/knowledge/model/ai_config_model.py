"""Database-backed AI provider configuration."""

from datetime import datetime
from typing import Literal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow

PURPOSE_CHAT: Literal["chat"] = "chat"
PURPOSE_EMBEDDING: Literal["embedding"] = "embedding"
PURPOSES = (PURPOSE_CHAT, PURPOSE_EMBEDDING)


class AiProviderConfigModel(Base):
    """One active provider configuration per purpose.

    API keys are stored as Fernet ciphertext; ``api_key_hint`` is the only
    human-readable trace and is safe to return to the browser.
    """

    __tablename__ = "ai_provider_config"
    __table_args__ = (
        UniqueConstraint("purpose", name="uq_ai_provider_config_purpose"),
        CheckConstraint("purpose IN ('chat', 'embedding')", name="purpose_valid"),
        CheckConstraint(
            "dimension IS NULL OR (dimension >= 16 AND dimension <= 4096)",
            name="dimension_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
