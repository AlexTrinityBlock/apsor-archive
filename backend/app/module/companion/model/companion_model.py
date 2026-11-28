"""ORM models for custom chat companions and the companion preference.

All three tables are private: every row carries ``user_id``, frames reference
their companion through the owner-safe ``(companion_id, user_id)`` pair, and the
migration forces an owner-only RLS policy on each table.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow

_ACTION_LIST = (
    "'idle', 'greet', 'listening', 'thinking', 'searching', 'reading', "
    "'writing', 'calculating', 'browsing', 'presenting', 'speaking', "
    "'waiting', 'success', 'confused', 'sleeping', 'held'"
)


class CompanionModel(Base):
    """One user-created companion whose frames are uploaded per action."""

    __tablename__ = "companion"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_companion_id_user_id"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),
        CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'other')",
            name="gender_valid",
        ),
        Index("ix_companion_user_id", "user_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_user_id_app_user",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
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


class CompanionFrameModel(Base):
    """One encoded AVIF (or fallback WebP) frame of a companion action.

    A frame's bytes never change after upload, so ``sha256`` is both the ETag
    and the cache-busting version. ``position`` orders frames within an action.
    """

    __tablename__ = "companion_frame"
    __table_args__ = (
        ForeignKeyConstraint(
            ["companion_id", "user_id"],
            ["companion.id", "companion.user_id"],
            name="fk_companion_frame_companion_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("storage_key", name="uq_companion_frame_storage_key"),
        CheckConstraint(f"action IN ({_ACTION_LIST})", name="action_valid"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "storage_backend IN ('local', 'r2', 's3')",
            name="storage_backend_valid",
        ),
        CheckConstraint(
            "mime_type IN ('image/avif', 'image/webp')",
            name="mime_type_valid",
        ),
        CheckConstraint(
            "width BETWEEN 1 AND 384 AND height BETWEEN 1 AND 576",
            name="dimensions_valid",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        Index(
            "ix_companion_frame_owner_action",
            "user_id",
            "companion_id",
            "action",
            "position",
        ),
        Index("ix_companion_frame_companion", "companion_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_frame_user_id_app_user",
        ),
        nullable=False,
    )
    companion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )


class CompanionPreferenceModel(Base):
    """One account's companion choice, visibility, motion level, and position."""

    __tablename__ = "companion_preference"
    __table_args__ = (
        CheckConstraint(
            "motion IN ('full', 'reduced', 'off')",
            name="motion_valid",
        ),
        CheckConstraint(
            "selected IS NULL OR char_length(selected) BETWEEN 1 AND 64",
            name="selected_length",
        ),
        CheckConstraint(
            "(position_x IS NULL) = (position_y IS NULL)",
            name="position_pair",
        ),
        CheckConstraint(
            "position_x IS NULL OR (position_x BETWEEN 0 AND 1 AND position_y BETWEEN 0 AND 1)",
            name="position_range",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_preference_user_id_app_user",
        ),
        primary_key=True,
    )
    selected: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    motion: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="full",
        server_default=text("'full'"),
    )
    position_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )


__all__ = ["CompanionFrameModel", "CompanionModel", "CompanionPreferenceModel"]
