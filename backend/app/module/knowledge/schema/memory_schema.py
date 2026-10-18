"""Schemas for memories, summaries, and their traceability graph."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryStatus = Literal["active", "deprecated"]
MemorySource = Literal["manual", "ai", "import"]
SummaryGenerator = Literal["deepseek", "extractive"]


class MemorySchema(BaseModel):
    """A memory as returned by the API."""

    model_config = ConfigDict(frozen=True)

    memory_id: int
    content: str
    status: MemoryStatus
    update_time: datetime
    supersedes_ids: list[int]
    superseded_by_id: int | None
    source: MemorySource
    created_at: datetime
    deleted_at: datetime | None


class MemoryCreateSchema(BaseModel):
    """The save_memory tool payload."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    supersedes: list[int] = Field(default_factory=list, max_length=50)
    occurred_at: datetime | None = None
    source: MemorySource = "manual"


class SummarySchema(BaseModel):
    """A periodic summary over a memory window."""

    model_config = ConfigDict(frozen=True)

    memory_summary_id: int
    content: str
    period_start: datetime
    period_end: datetime
    memory_count: int
    source_memory_ids: list[int]
    themes: list[str]
    generator: SummaryGenerator
    model: str | None
    created_at: datetime


class MemorySaveSchema(BaseModel):
    """The result of save_memory, including superseded rows and any new summary."""

    model_config = ConfigDict(frozen=True)

    memory: MemorySchema
    deprecated: list[MemorySchema]
    summary: SummarySchema | None


class MemoryReadSchema(BaseModel):
    """The read_memory tool result."""

    model_config = ConfigDict(frozen=True)

    target: MemorySchema
    neighbors_before: list[MemorySchema]
    neighbors_after: list[MemorySchema]
    supersedes: list[MemorySchema]
    superseded_by: MemorySchema | None
    chain: list[MemorySchema]


class SummaryCreateSchema(BaseModel):
    """Create a summary for an explicit set of memories or a period."""

    model_config = ConfigDict(extra="forbid")

    period_start: datetime | None = None
    period_end: datetime | None = None
    memory_ids: list[int] = Field(default_factory=list, max_length=500)
    force: bool = False
