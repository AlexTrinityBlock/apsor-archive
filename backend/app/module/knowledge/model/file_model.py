"""File records for the hierarchical File Library."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow


class FileModel(Base):
    """A stored file version.

    Re-uploading the same path creates a new row; the previous row is marked
    non-current instead of being deleted. Soft-deleted rows keep their id so a
    later insert never reuses it.
    """

    __tablename__ = "file"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_file_id_user_id"),
        ForeignKeyConstraint(
            ["supersedes_file_id", "user_id"],
            ["file.id", "file.user_id"],
            name="fk_file_supersedes_user",
            ondelete="SET NULL (supersedes_file_id)",
        ),
        Index(
            "uq_file_current_path",
            "user_id",
            "raw_file_path",
            unique=True,
            postgresql_where=text("is_current AND deleted_at IS NULL"),
        ),
        Index("ix_file_updated_at", "updated_at"),
        Index("ix_file_user_id_updated_at", "user_id", "updated_at"),
        Index(
            "ix_file_path_trgm",
            "raw_file_path",
            postgresql_using="gin",
            postgresql_ops={"raw_file_path": "gin_trgm_ops"},
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint(
            "storage_backend IN ('local', 'r2')",
            name="storage_backend_valid",
        ),
        CheckConstraint(
            "(storage_key IS NULL) = (storage_backend IS NULL)",
            name="storage_backend_key_pair",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_file_user_id_app_user",
        ),
        nullable=False,
    )
    raw_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    document_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="text", server_default="text"
    )
    extraction_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default="text", server_default="text"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_current: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
