"""ORM models for companion stories: persona/lore overrides, bonds, and recall.

All three tables are private (owner-only RLS):

- ``companion_story``: one account's copy-on-write story for one companion in
  one locale. A preset story references ``preset_id``; a custom companion's
  story references ``(companion_id, user_id)`` and cascades with it.
- ``companion_lore_fragment``: the fragments of one customized story.
- ``companion_bond``: completed runs per companion, which unlock lore tiers,
  and the run count at the last story moment.
- ``companion_lore_told``: the per-account progress through one companion's
  lore: which fragments were offered, how often, when, and by which path
  (topical recall, story moment, or self query). It drives recall and pacing
  and is the source of truth for root's progress view; users never see it.

Bond rows are keyed by the companion reference string so they stay
locale-independent; the service clears them when a custom companion is deleted.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow

_LOCALES = "'en', 'zh-TW', 'zh-CN'"
_TIERS = "'first', 'familiar', 'rare'"


class CompanionStoryModel(Base):
    """One account's persona and lore override for one companion and locale."""

    __tablename__ = "companion_story"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_companion_story_id_user_id"),
        ForeignKeyConstraint(
            ["companion_id", "user_id"],
            ["companion.id", "companion.user_id"],
            name="fk_companion_story_companion_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(preset_id IS NULL) <> (companion_id IS NULL)",
            name="one_target",
        ),
        CheckConstraint(f"locale IN ({_LOCALES})", name="locale_valid"),
        CheckConstraint(
            "persona IS NULL OR char_length(persona) BETWEEN 1 AND 4000",
            name="persona_length",
        ),
        Index(
            "uq_companion_story_preset",
            "user_id",
            "preset_id",
            "locale",
            unique=True,
            postgresql_where=sql_text("preset_id IS NOT NULL"),
        ),
        Index(
            "uq_companion_story_custom",
            "user_id",
            "companion_id",
            "locale",
            unique=True,
            postgresql_where=sql_text("companion_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_story_user_id_app_user",
        ),
        nullable=False,
    )
    preset_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    companion_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    lore_customized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
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


class CompanionLoreFragmentModel(Base):
    """One lore fragment of a customized story."""

    __tablename__ = "companion_lore_fragment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["story_id", "user_id"],
            ["companion_story.id", "companion_story.user_id"],
            name="fk_companion_lore_fragment_story_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("story_id", "fragment_key", name="uq_companion_lore_fragment_key"),
        CheckConstraint(f"tier IN ({_TIERS})", name="tier_valid"),
        CheckConstraint(
            "char_length(text) BETWEEN 1 AND 2000",
            name="text_length",
        ),
        CheckConstraint(
            "fragment_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'",
            name="fragment_key_format",
        ),
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_companion_lore_fragment_story", "user_id", "story_id", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_lore_fragment_user_id_app_user",
        ),
        nullable=False,
    )
    story_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fragment_key: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    themes: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    refs: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    edited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
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


class CompanionBondModel(Base):
    """Completed runs with one companion, and when each lore tier opened."""

    __tablename__ = "companion_bond"
    __table_args__ = (
        CheckConstraint("completed_runs >= 0", name="runs_non_negative"),
        CheckConstraint(
            "char_length(companion_ref) BETWEEN 1 AND 64",
            name="companion_ref_length",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_bond_user_id_app_user",
        ),
        primary_key=True,
    )
    companion_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    completed_runs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    familiar_unlocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rare_unlocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_story_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Distinct conversations with this companion (counted once per conversation
    # id, which only increases) and the count at the last life story.
    conversations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    last_conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_life_story_conversations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    admin_adjusted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sql_text("now()"),
    )


class CompanionLoreToldModel(Base):
    """One fragment of one companion that this account has been told."""

    __tablename__ = "companion_lore_told"
    __table_args__ = (
        CheckConstraint("told_count >= 1", name="told_count_positive"),
        CheckConstraint(
            "char_length(companion_ref) BETWEEN 1 AND 64",
            name="companion_ref_length",
        ),
        CheckConstraint(
            "fragment_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'",
            name="fragment_key_format",
        ),
        CheckConstraint(
            "source IN ('topical', 'story_moment', 'self_query', 'admin')",
            name="source_valid",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_companion_lore_told_user_id_app_user",
        ),
        primary_key=True,
    )
    companion_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    fragment_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    told_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # The path of the latest offer: topical | story_moment | self_query | admin.
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # When the fragment was first offered to this account.
    offered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    last_told_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )


__all__ = [
    "CompanionBondModel",
    "CompanionLoreFragmentModel",
    "CompanionLoreToldModel",
    "CompanionStoryModel",
]
