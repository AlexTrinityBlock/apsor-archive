"""Extractive fallback summarization.

The primary summary path is DeepSeek; this module is the deterministic fallback
used when no key is configured, the provider fails, or JSON parsing fails.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.shared.text.ngram import extract_themes


class SummaryMemoryInput(BaseModel):
    """A memory projected into the summary domain."""

    model_config = ConfigDict(frozen=True)

    memory_id: int
    memory_time: datetime
    content: str


class SummaryDraft(BaseModel):
    """A summary ready to be persisted."""

    model_config = ConfigDict(frozen=True)

    content: str
    themes: list[str]
    generator: Literal["deepseek", "extractive"]
    model: str | None


def _excerpt(content: str, limit: int = 140) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "\u2026"


def _evenly_spaced(items: list[SummaryMemoryInput], count: int) -> list[SummaryMemoryInput]:
    if len(items) <= count:
        return items
    if count == 1:
        return [items[0]]
    indexes = {round(index * (len(items) - 1) / (count - 1)) for index in range(count)}
    return [items[index] for index in sorted(indexes)]


def build_extractive_summary(memories: list[SummaryMemoryInput]) -> SummaryDraft:
    """Build a deterministic summary from evenly spaced memory excerpts."""
    ordered = sorted(memories, key=lambda memory: (memory.memory_time, memory.memory_id))
    if not ordered:
        raise ValueError("At least one memory is required.")

    selected = _evenly_spaced(ordered, 5)
    start = ordered[0].memory_time.date().isoformat()
    end = ordered[-1].memory_time.date().isoformat()
    header = f"{len(ordered)} memories from {start} to {end}."
    lines = [
        f"{memory.memory_time.date().isoformat()}: {_excerpt(memory.content)}"
        for memory in selected
    ]
    content = header + " " + " | ".join(lines)
    if len(content) > 1800:
        content = content[:1799].rstrip() + "\u2026"
    themes = extract_themes(memory.content for memory in ordered)
    return SummaryDraft(
        content=content,
        themes=themes,
        generator="extractive",
        model=None,
    )
