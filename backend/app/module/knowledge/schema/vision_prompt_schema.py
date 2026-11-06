"""Request and response contracts for the editable vision prompts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

VisionPromptSettingsSource = Literal["database", "default"]


class VisionPromptSettingsValuesSchema(BaseModel):
    """The two current templates, including any ``{language}`` placeholder."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    image_prompt: str
    document_prompt: str


class VisionPromptSettingsUpdateSchema(VisionPromptSettingsValuesSchema):
    """Replace both prompts in one root-only save."""


class VisionPromptSettingsReadSchema(BaseModel):
    """Current prompts, built-in defaults, fingerprints, and save warnings."""

    model_config = ConfigDict(frozen=True)

    config: VisionPromptSettingsValuesSchema
    defaults: VisionPromptSettingsValuesSchema
    source: VisionPromptSettingsSource
    updated_at: datetime | None
    max_chars: int
    required_keys: tuple[str, ...]
    image_prompt_sha256: str
    document_prompt_sha256: str
    warnings: list[str]


__all__ = [
    "VisionPromptSettingsReadSchema",
    "VisionPromptSettingsSource",
    "VisionPromptSettingsUpdateSchema",
    "VisionPromptSettingsValuesSchema",
]
