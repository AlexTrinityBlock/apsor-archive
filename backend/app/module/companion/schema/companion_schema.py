"""HTTP contracts for custom companions and the companion preference."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.module.companion.domain.companion_domain import (
    MAX_FRAMES_PER_ACTION,
    NAME_MAX_CHARS,
    SELECTION_MAX_CHARS,
    CompanionGender,
    CompanionMotion,
    parse_selection,
)
from app.shared.companion_action import CompanionAction


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise ValueError("name must not be blank.")
    if any(ord(character) < 32 for character in name):
        raise ValueError("name must not contain control characters.")
    return name


class CompanionFrameSchema(BaseModel):
    """One stored frame; ``url`` already carries the cache-busting version."""

    id: int
    action: CompanionAction
    position: int
    width: int
    height: int
    size_bytes: int
    version: str
    url: str


class CompanionSchema(BaseModel):
    """One custom companion with every frame, ordered by action and position."""

    id: int
    name: str
    gender: CompanionGender | None
    frames: list[CompanionFrameSchema]
    created_at: datetime
    updated_at: datetime


class CompanionCreateSchema(BaseModel):
    """Create an empty companion; frames are uploaded per action afterwards."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=NAME_MAX_CHARS)
    gender: CompanionGender | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_name(value)


class CompanionUpdateSchema(BaseModel):
    """Rename a companion or change its gender; omitted fields are unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_CHARS)
    gender: CompanionGender | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("name must not be null.")
        return _clean_name(value)


class CompanionFrameOrderSchema(BaseModel):
    """The complete new order of one action's frames."""

    model_config = ConfigDict(extra="forbid")

    action: CompanionAction
    frame_ids: list[int] = Field(min_length=1, max_length=MAX_FRAMES_PER_ACTION)

    @field_validator("frame_ids")
    @classmethod
    def _validate_ids(cls, value: list[int]) -> list[int]:
        if any(frame_id <= 0 for frame_id in value):
            raise ValueError("frame ids must be positive.")
        if len(set(value)) != len(value):
            raise ValueError("frame ids must be unique.")
        return value


class CompanionPositionSchema(BaseModel):
    """A normalized viewport position, where 0..1 spans the visible area."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class CompanionPreferenceSchema(BaseModel):
    """The account's companion choice. ``selected=None`` means the default preset."""

    selected: str | None
    enabled: bool
    motion: CompanionMotion
    position: CompanionPositionSchema | None
    updated_at: datetime | None


class CompanionPreferenceUpdateSchema(BaseModel):
    """Change part of the preference; omitted fields keep their stored value."""

    model_config = ConfigDict(extra="forbid")

    selected: str | None = Field(default=None, max_length=SELECTION_MAX_CHARS)
    enabled: bool | None = None
    motion: CompanionMotion | None = None
    position: CompanionPositionSchema | None = None

    @field_validator("selected")
    @classmethod
    def _validate_selected(cls, value: str | None) -> str | None:
        if value is not None and parse_selection(value) is None:
            raise ValueError("selected must be 'preset:<id>' or 'custom:<id>'.")
        return value

    @field_validator("enabled", "motion")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("value must not be null.")
        return value


__all__ = [
    "CompanionCreateSchema",
    "CompanionFrameOrderSchema",
    "CompanionFrameSchema",
    "CompanionPositionSchema",
    "CompanionPreferenceSchema",
    "CompanionPreferenceUpdateSchema",
    "CompanionSchema",
    "CompanionUpdateSchema",
]
