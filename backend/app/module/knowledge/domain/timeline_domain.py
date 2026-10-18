"""Sparse timeline sampling with proportional anchors and skip accounting."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict

TimelineKind = Literal["memory", "summary", "file_update"]


class TimelineEvent(BaseModel):
    """A normalized event from any knowledge source."""

    model_config = ConfigDict(frozen=True)

    kind: TimelineKind
    source_id: int
    time: datetime
    date_label: str
    content: str
    title: str | None = None
    action: str | None = None
    status: str | None = None
    raw_file_path: str | None = None


class TimelineSelection(BaseModel):
    """A selected event and the fraction of the range it represents."""

    model_config = ConfigDict(frozen=True)

    event: TimelineEvent
    anchor: float


class TimelineSkip(BaseModel):
    """Unselected events between two sampled events."""

    model_config = ConfigDict(frozen=True)

    from_time: datetime
    to_time: datetime
    file_number: int
    memory_number: int
    summary_number: int


class TimelineDensity(BaseModel):
    """Per-day event counts for the density strip."""

    model_config = ConfigDict(frozen=True)

    date: str
    file_count: int
    memory_count: int
    summary_count: int


class TimelineSample(BaseModel):
    """The sparse timeline payload before it is mapped to response schemas."""

    model_config = ConfigDict(frozen=True)

    selections: tuple[TimelineSelection, ...]
    skips: tuple[TimelineSkip, ...]
    density: tuple[TimelineDensity, ...]
    total: int
    truncated: bool


def _anchor_time(start: datetime, end: datetime, fraction: float) -> datetime:
    return start + (end - start) * fraction


def _skip_counts(events: list[TimelineEvent]) -> tuple[int, int, int]:
    counts = Counter(event.kind for event in events)
    return counts["file_update"], counts["memory"], counts["summary"]


def sample_timeline(
    events: list[TimelineEvent],
    *,
    start: datetime,
    end: datetime,
    anchors: int = 5,
    truncated: bool = False,
) -> TimelineSample:
    """Select up to ``anchors`` events per kind and describe what was skipped."""
    if end <= start:
        raise ValueError("The timeline end must be after its start.")
    if anchors < 1:
        raise ValueError("anchors must be at least 1")

    by_kind: dict[str, list[TimelineEvent]] = defaultdict(list)
    for event in events:
        by_kind[event.kind].append(event)

    selected: dict[tuple[str, int], TimelineSelection] = {}
    for kind, kind_events in by_kind.items():
        kind_events.sort(key=lambda event: (event.time, event.source_id))
        for index in range(anchors):
            fraction = 0.0 if anchors == 1 else index / (anchors - 1)
            target = _anchor_time(start, end, fraction)
            remaining = [
                event
                for event in kind_events
                if (event.kind, event.source_id) not in selected
            ]
            if not remaining:
                break
            nearest = min(
                remaining,
                key=lambda event: (abs((event.time - target).total_seconds()), event.time),
            )
            selected[(kind, nearest.source_id)] = TimelineSelection(
                event=nearest,
                anchor=fraction,
            )

    selections = sorted(
        selected.values(),
        key=lambda selection: (
            selection.event.time,
            selection.event.kind,
            selection.event.source_id,
        ),
    )
    selected_keys = {
        (selection.event.kind, selection.event.source_id) for selection in selections
    }

    skips: list[TimelineSkip] = []
    for previous, current in pairwise(selections):
        between = [
            event
            for event in events
            if previous.event.time < event.time < current.event.time
            and (event.kind, event.source_id) not in selected_keys
        ]
        if not between:
            continue
        file_number, memory_number, summary_number = _skip_counts(between)
        skips.append(
            TimelineSkip(
                from_time=previous.event.time,
                to_time=current.event.time,
                file_number=file_number,
                memory_number=memory_number,
                summary_number=summary_number,
            )
        )

    density_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        density_counts[event.date_label][event.kind] += 1
    density = tuple(
        TimelineDensity(
            date=date_label,
            file_count=counter["file_update"],
            memory_count=counter["memory"],
            summary_count=counter["summary"],
        )
        for date_label, counter in sorted(density_counts.items())
    )

    return TimelineSample(
        selections=tuple(selections),
        skips=tuple(skips),
        density=density,
        total=len(events),
        truncated=truncated,
    )


def day_range_bounds(date: datetime, day_range: int) -> tuple[datetime, datetime]:
    """Return inclusive start and exclusive end for a day range."""
    if day_range < 1:
        raise ValueError("day_range must be at least 1")
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=day_range)
    return start, end
