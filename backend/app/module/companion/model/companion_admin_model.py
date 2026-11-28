"""ORM models root manages for one account's companion (user reads, never writes).

These private tables carry ``{table}_owner_read`` (the account may read its
own row so it can resolve its companion) and ``{table}_companion_admin``
(root, under the companion admin scope, may write). The database therefore
guarantees that an account cannot alter what root configured for it.

- ``companion_account_policy``: default companion, allowed set, optional pin.
- ``companion_user_config``: per-account overrides of story tunables
  (NULL inherits the global ``companion_config``).
- ``companion_admin_story_override`` / ``companion_admin_lore_override``:
  root's persona and lore layer for one account, below the user's own edits.
- ``companion_admin_access_log``: append-only audit of root reading or
  changing a user's companion story.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class _TimestampsMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sql_text("now()"),
    )


def _owner_id() -> Mapped[int]:
    return mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        primary_key=True,
    )


def _jsonb_list() -> Mapped[list[Any]]:
    return mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )


class CompanionAccountPolicyModel(_TimestampsMixin, Base):
    """Root's companion policy for one account."""

    __tablename__ = "companion_account_policy"

    user_id: Mapped[int] = _owner_id()
    default_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # NULL means every enabled preset plus the account's own custom companions.
    allowed_refs: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    allow_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pinned_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CompanionUserConfigModel(_TimestampsMixin, Base):
    """Root's per-account overrides of the story tunables (NULL inherits)."""

    __tablename__ = "companion_user_config"

    user_id: Mapped[int] = _owner_id()
    familiar_unlock_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rare_unlock_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_recalled_fragments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    topical_min_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    untold_bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    told_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    told_penalty_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    story_moment_every_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    self_query_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_contributions_per_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    life_story_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    life_story_every_conversations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    life_story_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    life_story_max_per_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    life_story_require_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CompanionAdminStoryOverrideModel(_TimestampsMixin, Base):
    """Root's persona for one account, companion, and locale."""

    __tablename__ = "companion_admin_story_override"

    user_id: Mapped[int] = _owner_id()
    companion_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    persona: Mapped[str] = mapped_column(Text, nullable=False)


class CompanionAdminLoreOverrideModel(_TimestampsMixin, Base):
    """Root's replace / add / hide of one lore fragment for one account."""

    __tablename__ = "companion_admin_lore_override"

    user_id: Mapped[int] = _owner_id()
    companion_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    fragment_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    themes: Mapped[list[Any]] = _jsonb_list()
    refs: Mapped[list[Any]] = _jsonb_list()
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CompanionAdminAccessLogModel(Base):
    """One root read or change of a user's companion story (append-only)."""

    __tablename__ = "companion_admin_access_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    story_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    companion_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )


__all__ = [
    "CompanionAccountPolicyModel",
    "CompanionAdminAccessLogModel",
    "CompanionAdminLoreOverrideModel",
    "CompanionAdminStoryOverrideModel",
    "CompanionUserConfigModel",
]
