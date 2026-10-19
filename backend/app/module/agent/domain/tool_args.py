"""Validated argument models for every agent tool."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ToolArgs(BaseModel):
    """Base class: reject unknown model arguments instead of ignoring them."""

    model_config = ConfigDict(extra="forbid")


class SearchKnowledgeArgs(_ToolArgs):
    """Arguments for hybrid archive search."""

    query: str = Field(min_length=1, max_length=200)
    result_number: int = Field(default=8, ge=1, le=20)
    include_history: bool = False


class ReadFileArgs(_ToolArgs):
    """Arguments for a bounded file chunk window."""

    file_id: int = Field(gt=0)
    chunk: int = Field(default=1, ge=1)
    chunk_range: int = Field(default=1, ge=0, le=25)


class ReadTimelineArgs(_ToolArgs):
    """Arguments for the sparse timeline."""

    year: int = Field(ge=1970, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    day_range: int = Field(default=7, ge=1, le=366)
    include_history: bool = False


class ReadPathArgs(_ToolArgs):
    """Arguments for listing one library path."""

    path: str = Field(default="/", min_length=1, max_length=1024)
    path_depth: int = Field(default=2, ge=1, le=10)
    fuzzy_search: str | None = Field(default=None, max_length=128)


class ReadMemoryArgs(_ToolArgs):
    """Arguments for reading a memory and its chain."""

    memory_id: int = Field(gt=0)
    memory_range: int = Field(default=2, ge=0, le=10)
    trace_history: bool = True


class SaveMemoryArgs(_ToolArgs):
    """Arguments for an explicitly confirmed memory write."""

    content: str = Field(min_length=1, max_length=8000)
    supersedes: list[int] = Field(default_factory=list, max_length=50)
    occurred_at: datetime | None = None
    user_confirmed: bool = Field(
        description=(
            "Set to true only after the user explicitly asked to save this memory "
            "and confirmed the content in the current conversation."
        )
    )


class SearchMediaArgs(_ToolArgs):
    """Arguments for image caption/tag search."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=12, ge=1, le=24)


class GetMediaArgs(_ToolArgs):
    """Arguments for one media asset."""

    media_id: int = Field(gt=0)


class PresentResourceArgs(_ToolArgs):
    """Arguments for a viewer card."""

    resource_type: Literal["file", "media", "memory"]
    resource_id: int = Field(gt=0)
    chunk: int | None = Field(default=None, ge=1)
