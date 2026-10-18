"""Standalone media models for multimodal retrieval."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class MediaModel(Base):
    """One image asset with a searchable caption and a visual vector.

    Media is deliberately separate from the text File Library: it has its own
    table, its own n-gram index, and its own UI route.
    """

    __tablename__ = "media_asset"
    __table_args__ = (
        Index(
            "uq_media_asset_current_path",
            "raw_file_path",
            unique=True,
            postgresql_where=text("is_current AND deleted_at IS NULL"),
        ),
        Index("ix_media_asset_created_at", "created_at"),
        Index("ix_media_asset_content_hash", "content_hash"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    raw_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, default="image")
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visual_embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_current: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaNgramModel(Base):
    """Inverted n-gram index over caption and tags."""

    __tablename__ = "media_ngram"
    __table_args__ = (Index("ix_media_ngram_gram", "gram"),)

    media_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("media_asset.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gram: Mapped[str] = mapped_column(Text, primary_key=True)
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
