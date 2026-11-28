"""ORM models for global, root-editable companion world content.

The files under ``companion/lore`` are seed data; these global tables
(read-all, root-write RLS) hold the live copy: presets and their localized
persona, preset lore items and text, canon entities, world documents with a
short revision history, the story-config singleton, prompt templates, and the
seed state. Seeded rows record ``seed_hash`` (the shipped text),
``upstream_seed_hash`` (a newer shipped text waiting for review when root has
edited the row), and ``admin_modified``.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    SmallInteger,
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


class _SeedTrackedMixin:
    """Provenance columns shared by every seeded, root-editable row."""

    seed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upstream_seed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admin_modified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sql_text("now()"),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )


def _jsonb_list() -> Mapped[list[Any]]:
    return mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )


class CompanionPresetModel(_SeedTrackedMixin, Base):
    """One preset librarian: order, availability, and the global default flag."""

    __tablename__ = "companion_preset"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_global_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CompanionPresetTextModel(_SeedTrackedMixin, Base):
    """A preset's localized name and persona."""

    __tablename__ = "companion_preset_text"

    preset_id: Mapped[str] = mapped_column(
        String(48),
        ForeignKey("companion_preset.id", ondelete="CASCADE"),
        primary_key=True,
    )
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False)


class CompanionLoreItemModel(_SeedTrackedMixin, Base):
    """One preset lore fragment (locale-independent metadata)."""

    __tablename__ = "companion_lore_item"
    __table_args__ = (
        UniqueConstraint(
            "preset_id",
            "fragment_key",
            name="uq_companion_lore_item_preset_id_fragment_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    preset_id: Mapped[str] = mapped_column(
        String(48),
        ForeignKey("companion_preset.id", ondelete="CASCADE"),
        nullable=False,
    )
    fragment_key: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[str] = mapped_column(String(16), nullable=False)
    themes: Mapped[list[Any]] = _jsonb_list()
    refs: Mapped[list[Any]] = _jsonb_list()
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanionLoreItemTextModel(_SeedTrackedMixin, Base):
    """One preset lore fragment's text in one locale."""

    __tablename__ = "companion_lore_item_text"

    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("companion_lore_item.id", ondelete="CASCADE"),
        primary_key=True,
    )
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class CompanionCanonEntityModel(_SeedTrackedMixin, Base):
    """A canon entity's localized name and summary."""

    __tablename__ = "companion_canon_entity"

    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class CompanionWorldDocModel(_SeedTrackedMixin, Base):
    """A world document (bible, glossary, world, terms, character) in one locale."""

    __tablename__ = "companion_world_doc"

    doc_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CompanionWorldDocRevisionModel(Base):
    """A previous version of a world document."""

    __tablename__ = "companion_world_doc_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["doc_key", "locale"],
            ["companion_world_doc.doc_key", "companion_world_doc.locale"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_key: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )


class CompanionConfigModel(_SeedTrackedMixin, Base):
    """The singleton of every companion-story tunable (global defaults)."""

    __tablename__ = "companion_config"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    max_recalled_fragments: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    topical_min_similarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.30)
    untold_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.06)
    told_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.04)
    told_penalty_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    story_moment_every_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    self_query_window: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    max_contributions_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    self_query_phrases: Mapped[list[Any]] = _jsonb_list()
    self_canon_terms: Mapped[list[Any]] = _jsonb_list()
    banned_address_terms: Mapped[list[Any]] = _jsonb_list()
    life_story_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    life_story_every_conversations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    life_story_weight: Mapped[str] = mapped_column(String(16), nullable=False, default="past")
    life_story_max_per_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    life_story_memory_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    life_story_memory_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=6000)
    life_story_canon_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    life_story_max_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1500,
    )
    life_story_max_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=2400)
    life_story_require_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    life_story_poll_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    life_story_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CompanionPromptTemplateModel(_SeedTrackedMixin, Base):
    """A guidance string or prompt template in one locale."""

    __tablename__ = "companion_prompt_template"

    template_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    required_placeholders: Mapped[list[Any]] = _jsonb_list()
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CompanionSeedStateModel(Base):
    """Which seed bundle has been applied, and the live content version."""

    __tablename__ = "companion_seed_state"

    bundle: Mapped[str] = mapped_column(String(48), primary_key=True)
    seed_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )


__all__ = [
    "CompanionCanonEntityModel",
    "CompanionConfigModel",
    "CompanionLoreItemModel",
    "CompanionLoreItemTextModel",
    "CompanionPresetModel",
    "CompanionPresetTextModel",
    "CompanionPromptTemplateModel",
    "CompanionSeedStateModel",
    "CompanionWorldDocModel",
    "CompanionWorldDocRevisionModel",
]
