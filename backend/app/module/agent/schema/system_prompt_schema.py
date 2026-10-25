"""HTTP request and response contracts for system prompt sections."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemPromptSectionReadSchema(BaseModel):
    """One persisted custom section returned to the browser."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    title: str
    body: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class SystemPromptBuiltinSectionSchema(BaseModel):
    """One built-in prompt section, with its effective body and edit state."""

    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    body: str
    customized: bool
    updated_at: datetime | None


class SystemPromptBuiltinUpdateSchema(BaseModel):
    """Replace one built-in section body; titles and order stay canonical."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=32000)


class SystemPromptSectionCreateSchema(BaseModel):
    """Create one section.

    The schema does not strip whitespace: the service trims both fields and
    raises ``agent_invalid_system_prompt`` for whitespace-only input, so the
    browser gets the same stable error code for blank and too-short values.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=32000)
    # ``None`` means "append at max(sort_order) + 10"; an explicit value is
    # honored so imports and tests can place a section between existing rows.
    sort_order: int | None = Field(default=None, ge=0)


class SystemPromptSectionUpdateSchema(BaseModel):
    """Replace one section; omitted ``sort_order`` preserves the current value."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=32000)
    sort_order: int | None = Field(default=None, ge=0)


class SystemPromptReorderSchema(BaseModel):
    """The complete new order; every existing section id must appear once."""

    model_config = ConfigDict(extra="forbid")

    section_ids: list[int] = Field(min_length=1, max_length=100)


__all__ = [
    "SystemPromptBuiltinSectionSchema",
    "SystemPromptBuiltinUpdateSchema",
    "SystemPromptReorderSchema",
    "SystemPromptSectionCreateSchema",
    "SystemPromptSectionReadSchema",
    "SystemPromptSectionUpdateSchema",
]
