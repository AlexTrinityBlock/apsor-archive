"""Request and response schemas for companion personas and lore."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.module.companion.domain.story_domain import (
    FRAGMENT_MAX_CHARS,
    MAX_THEMES_PER_FRAGMENT,
    PERSONA_MAX_CHARS,
    THEME_MAX_CHARS,
)

StoryLocaleField = Literal["en", "zh-TW", "zh-CN"]
LoreTierField = Literal["first", "familiar", "rare"]


class CompanionPersonaSchema(BaseModel):
    """The persona a companion speaks with in this account and locale."""

    companion_ref: str
    locale: StoryLocaleField
    name: str
    persona: str
    is_default: bool = Field(description="True when no account override exists.")
    default_persona: str
    updated_at: datetime | None = None


class CompanionPersonaUpdateSchema(BaseModel):
    """Replace this account's persona for one companion and locale."""

    model_config = ConfigDict(extra="forbid")

    persona: str = Field(min_length=1, max_length=PERSONA_MAX_CHARS)

    @field_validator("persona")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("persona must not be blank")
        return stripped


class CompanionLoreFragmentSchema(BaseModel):
    """One lore fragment the account may see in its story editor.

    The account sees only its own fragments and the ones it has already heard;
    tiers, locks, and progress stay hidden (root sees them in administration).
    """

    id: str
    themes: list[str]
    text: str
    edited: bool
    own: bool = Field(description="Written by the account (its own memory of the companion).")
    heard: bool = Field(description="Already surfaced to the account at least once.")
    position: int


class CompanionLoreSchema(BaseModel):
    """A companion's visible lore in one locale, for the story editor."""

    companion_ref: str
    locale: StoryLocaleField
    name: str
    customized: bool = Field(description="True when this locale's lore is an account copy.")
    fragments: list[CompanionLoreFragmentSchema]


class _ThemesMixin(BaseModel):
    @field_validator("themes", check_fields=False)
    @classmethod
    def _themes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > MAX_THEMES_PER_FRAGMENT:
            raise ValueError(f"at most {MAX_THEMES_PER_FRAGMENT} themes")
        if any(len(item) > THEME_MAX_CHARS for item in value):
            raise ValueError(f"each theme is at most {THEME_MAX_CHARS} characters")
        return value


class CompanionLoreCreateSchema(_ThemesMixin):
    """Add one fragment to this account's copy of the lore."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=FRAGMENT_MAX_CHARS)
    themes: list[str] = Field(default_factory=list)
    tier: LoreTierField = "first"


class CompanionLoreUpdateSchema(_ThemesMixin):
    """Edit one fragment; omitted fields keep their values."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=FRAGMENT_MAX_CHARS)
    themes: list[str] | None = None
    tier: LoreTierField | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)


__all__ = [
    "CompanionLoreCreateSchema",
    "CompanionLoreFragmentSchema",
    "CompanionLoreSchema",
    "CompanionLoreUpdateSchema",
    "CompanionPersonaSchema",
    "CompanionPersonaUpdateSchema",
    "LoreTierField",
    "StoryLocaleField",
]
