"""HTTP request and response contracts for frequently used prompts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FrequentlyUsedPromptReadSchema(BaseModel):
    """One persisted prompt shortcut returned to the browser."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    title: str
    prompt_text: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FrequentlyUsedPromptCreateSchema(BaseModel):
    """Create a prompt shortcut.

    The schema deliberately does not strip whitespace: the service strips the
    values and raises ``invalid_frequent_prompt`` for whitespace-only input, so
    the frontend receives our stable error code instead of FastAPI's generic
    validation message.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    prompt_text: str = Field(min_length=1, max_length=4000)
    sort_order: int = Field(default=0, ge=0)


class FrequentlyUsedPromptUpdateSchema(BaseModel):
    """Replace every editable field of one prompt shortcut."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    prompt_text: str = Field(min_length=1, max_length=4000)
    sort_order: int = Field(default=0, ge=0)


class FrequentlyUsedPromptReorderSchema(BaseModel):
    """The complete new order; every existing prompt id must appear once."""

    model_config = ConfigDict(extra="forbid")

    prompt_ids: list[int] = Field(min_length=1, max_length=20)


__all__ = [
    "FrequentlyUsedPromptCreateSchema",
    "FrequentlyUsedPromptReadSchema",
    "FrequentlyUsedPromptReorderSchema",
    "FrequentlyUsedPromptUpdateSchema",
]
