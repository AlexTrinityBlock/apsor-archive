"""Schemas for the sparsely sampled timeline."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TimelineKind = Literal["memory", "summary", "file_update"]


class TimelineEventSchema(BaseModel):
    """One sampled timeline event."""

    model_config = ConfigDict(frozen=True)

    kind: TimelineKind
    anchor: float
    time: datetime
    content: str
    memory_id: int | None = None
    memory_summary_id: int | None = None
    file_id: int | None = None
    raw_file_path: str | None = None
    action: str | None = None
    status: str | None = None
    # Summary events only: coverage metadata makes the compressed view explicit.
    memory_count: int | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class TimelineSkipSchema(BaseModel):
    """A count of events omitted between two samples."""

    model_config = ConfigDict(frozen=True)

    from_time: datetime
    to_time: datetime
    file_number: int
    memory_number: int
    summary_number: int


class TimelineDensitySchema(BaseModel):
    """Per-day counts used by the density strip."""

    model_config = ConfigDict(frozen=True)

    date: str
    file_count: int
    memory_count: int
    summary_count: int


class TimelineResponseSchema(BaseModel):
    """The read_timeline tool result."""

    model_config = ConfigDict(frozen=True)

    range_start: datetime
    range_end: datetime
    day_range: int
    sampled: int
    total: int
    skipped: int
    truncated: bool
    events: list[TimelineEventSchema]
    skips: list[TimelineSkipSchema]
    density: list[TimelineDensitySchema]
