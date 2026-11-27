"""Tiny WebP thumbnails rendered once per file version."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow

THUMBNAIL_STATUS_READY = "ready"
THUMBNAIL_STATUS_NONE = "none"
THUMBNAIL_STATUS_FAILED = "failed"
THUMBNAIL_STATUSES = (
    THUMBNAIL_STATUS_READY,
    THUMBNAIL_STATUS_NONE,
    THUMBNAIL_STATUS_FAILED,
)


class FileThumbnailModel(Base):
    """One owner-scoped thumbnail row for an immutable file version.

    ``data`` is deferred so metadata reads (width, height, hash) never pull the
    image bytes. The composite foreign key keeps the thumbnail in the same
    account as its file and cascades when a staged file is discarded.
    """

    __tablename__ = "file_thumbnail"
    __table_args__ = (
        ForeignKeyConstraint(
            ["file_id", "user_id"],
            ["file.id", "file.user_id"],
            name="fk_file_thumbnail_file_user",
            ondelete="CASCADE",
        ),
        Index("ix_file_thumbnail_user_id", "user_id"),
        CheckConstraint("status IN ('ready', 'none', 'failed')", name="status_valid"),
        CheckConstraint(
            "(status = 'ready') = (data IS NOT NULL) "
            "AND (status = 'ready') = (sha256 IS NOT NULL) "
            "AND (status = 'ready') = (width IS NOT NULL) "
            "AND (status = 'ready') = (height IS NOT NULL)",
            name="ready_payload",
        ),
        CheckConstraint("data IS NULL OR octet_length(data) <= 32768", name="data_size"),
        CheckConstraint("width IS NULL OR (width BETWEEN 1 AND 512)", name="width_range"),
        CheckConstraint("height IS NULL OR (height BETWEEN 1 AND 512)", name="height_range"),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256_format"),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
    )

    file_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_file_thumbnail_user_id_app_user",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generator_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
