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
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
            "AND cached_tokens >= 0 AND api_calls >= 0 AND agent_turns >= 0 "
            "AND embedding_characters >= 0 AND web_search_calls >= 0 "
            "AND web_fetch_calls >= 0",
            name="usage_non_negative",
        ),
        CheckConstraint(
            "(chat_granted IS NULL OR chat_granted >= 0) "
            "AND (embedding_granted IS NULL OR embedding_granted >= 0) "
            "AND (web_search_granted IS NULL OR web_search_granted >= 0) "
            "AND (web_fetch_granted IS NULL OR web_fetch_granted >= 0) "
            "AND chat_used_before_reset >= 0 "
            "AND embedding_used_before_reset >= 0 "
            "AND web_search_used_before_reset >= 0 "
            "AND web_fetch_used_before_reset >= 0",
            name="quota_non_negative",
        ),
        CheckConstraint(
            "chat_model IS NULL OR char_length(chat_model) BETWEEN 1 AND 128",
            name="chat_model_length",
        ),
        CheckConstraint(
            "aux_model IS NULL OR char_length(aux_model) BETWEEN 1 AND 128",
            name="aux_model_length",
        ),
        CheckConstraint(
            "chat_reasoning_effort IS NULL "
            "OR char_length(chat_reasoning_effort) BETWEEN 1 AND 32",
            name="chat_effort_length",
        ),
        CheckConstraint(
            "aux_reasoning_effort IS NULL OR char_length(aux_reasoning_effort) BETWEEN 1 AND 32",
            name="aux_effort_length",
        ),
        CheckConstraint(
            "chat_context_window_tokens IS NULL "
            "OR chat_context_window_tokens BETWEEN 8000 AND 2000000",
            name="chat_context_window",
        ),
        CheckConstraint(
            "chat_compaction_threshold_tokens IS NULL "
            "OR chat_compaction_threshold_tokens BETWEEN 1000 AND 1000000",
            name="chat_compaction_threshold",
        ),
        CheckConstraint(
            "chat_compaction_threshold_tokens IS NULL "
            "OR chat_context_window_tokens IS NULL "
            "OR chat_compaction_threshold_tokens < chat_context_window_tokens",
            name="chat_context_order",
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
    prompt_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cached_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    api_calls: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    agent_turns: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_agent_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-category usage allowances. ``*_used_before_reset`` is the lifetime
    # counter value captured by the last admin reset, so the current cycle is
    # ``max(0, lifetime - used_before_reset)``. A NULL grant is unlimited; the
    # enabled flag still wins over an unlimited grant.
    chat_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    chat_granted: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chat_used_before_reset: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    embedding_characters: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    embedding_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    embedding_granted: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    embedding_used_before_reset: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    web_search_calls: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    web_search_granted: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    web_search_used_before_reset: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    web_fetch_calls: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    web_fetch_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    web_fetch_granted: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    web_fetch_used_before_reset: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    # Two chat endpoints per account: ``chat_*`` serves the agent loop and
    # ``aux_*`` serves summaries, memory, ingest extraction, and vision. The
    # row id and the model are a pair: both NULL means unassigned, a row id with
    # no model means the endpoint was deleted. The foreign key is the only
    # cross-slice schema edge (auth -> knowledge) and is intentional, because
    # the assignment must point at the row whose URL and key serve the model.
    # app_user stays outside RLS, so these columns use the same root-read/write
    # path the quota columns already use.
    chat_provider_config_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "chat_provider_config.id",
            ondelete="SET NULL",
            name="fk_app_user_chat_provider_config_id_chat_provider_config",
        ),
        nullable=True,
    )
    chat_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chat_reasoning_effort: Mapped[str | None] = mapped_column(String(32), nullable=True)
    aux_provider_config_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "chat_provider_config.id",
            ondelete="SET NULL",
            name="fk_app_user_aux_provider_config_id_chat_provider_config",
        ),
        nullable=True,
    )
    aux_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aux_reasoning_effort: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    chat_context_window_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat_compaction_threshold_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


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
        Index("ix_user_session_impersonator_user_id", "impersonator_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    impersonator_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="CASCADE",
            name="fk_user_session_impersonator_user_id_app_user",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
