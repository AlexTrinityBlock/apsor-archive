"""HTTP schemas for the custom system prompt."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemPromptReadSchema(BaseModel):
    """The persisted prompt and whether it adds a custom first section."""

    model_config = ConfigDict(frozen=True)

    title: str
    body: str
    is_custom: bool
    updated_at: datetime | None


class SystemPromptUpdateSchema(BaseModel):
    """Replace the custom prompt; both fields are required after trimming."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=32_000)
