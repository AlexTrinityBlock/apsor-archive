"""Account, role, and cookie-session models."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class AppUserModel(Base):
    """One archive account.

    Exactly one account has ``role='root'``; the partial unique index enforces
    that invariant. Every other account is a private-archive ``user``. Accounts
    are disabled instead of deleted so usernames and archive ownership remain
    stable.
    """

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(
            "display_name IS NULL OR char_length(display_name) BETWEEN 1 AND 80",
            name="display_name_length",
        ),
        CheckConstraint("role IN ('root', 'user')", name="role_valid"),
        CheckConstraint(
            "(is_active AND disabled_at IS NULL) OR (NOT is_active AND disabled_at IS NOT NULL)",
            name="active_disabled",
        ),
        Index(
            "uq_app_user_single_root",
            "role",
            unique=True,
            postgresql_where=text("role = 'root'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="user",
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_app_user_created_by_user_id_app_user",
        ),
        nullable=True,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserProfileCardModel(Base):
    """One ordered, user-authored card describing the archive owner."""

    __tablename__ = "user_profile_card"
    __table_args__ = (
        CheckConstraint(
            "char_length(title) BETWEEN 1 AND 120",
            name="title_length",
        ),
        CheckConstraint(
            "char_length(content) BETWEEN 1 AND 2000",
            name="content_length",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order"),
        Index("ix_user_profile_card_order", "user_id", "sort_order", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
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


class UserSessionModel(Base):
    """A browser session. Only the SHA-256 hash of the cookie token is stored."""

    __tablename__ = "user_session"
    __table_args__ = (
        Index("ix_user_session_token_hash", "token_hash", unique=True),
        Index("ix_user_session_expires_at", "expires_at"),
        Index("ix_user_session_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
