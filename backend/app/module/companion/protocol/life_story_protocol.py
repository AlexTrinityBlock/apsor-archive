"""Ports the life-story worker depends on.

A life story is written by the account's own assigned model from a bounded set
of the account's own memories plus the world canon. The worker reaches the
archive only through :class:`LifeStoryMaterialSelectorProtocol` (implemented
in ``companion/dependencies.py`` over the knowledge slice, inside the owner's
RLS session) and the model only through :class:`LifeStoryTextGeneratorProtocol`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from app.module.companion.model.companion_life_story_model import (
    CompanionGeneratedStoryModel,
    CompanionStoryJobModel,
)

MaterialKind = Literal["memory", "file"]


@dataclass(frozen=True)
class LifeStoryMaterial:
    """One bounded excerpt of the account's own archive offered to the writer."""

    kind: MaterialKind
    source_id: int
    title: str
    excerpt: str


@dataclass(frozen=True)
class LifeStoryMaterialRequest:
    """What the selector may return: a bounded, deduplicated selection."""

    limit: int
    max_chars: int
    seed_themes: tuple[str, ...] = ()
    exclude_memory_ids: frozenset[int] = field(default_factory=frozenset)
    exclude_file_ids: frozenset[int] = field(default_factory=frozenset)


class LifeStoryMaterialSelectorProtocol(Protocol):
    """Pick a bounded, relevant set of the account's own memories and files."""

    async def select(self, request: LifeStoryMaterialRequest) -> list[LifeStoryMaterial]: ...


@dataclass(frozen=True)
class LifeStoryGeneration:
    """The model's raw output and usage for one life story."""

    text: str
    model: str | None = None
    provider_config_id: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LifeStoryTextGeneratorProtocol(Protocol):
    """Generate text with the account's own assigned (auxiliary) model."""

    async def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, str]],
        max_output_tokens: int,
    ) -> LifeStoryGeneration: ...


class GeneratedStoryRowProtocol(Protocol):
    """The fields recall needs from one stored life story."""

    fragment_key: str
    text: str
    weight: str
    themes: list[Any]


class GeneratedStorySourceProtocol(Protocol):
    """Read the account's published life stories for one companion and locale."""

    async def list_published(
        self,
        companion_ref: str,
        locale: str,
    ) -> Sequence[GeneratedStoryRowProtocol]: ...


class LifeStoryRepositoryProtocol(GeneratedStorySourceProtocol, Protocol):
    """Owner-scoped persistence of life-story jobs, stories, and bond counters."""

    async def record_conversation(
        self,
        companion_ref: str,
        conversation_id: int,
        now: datetime,
    ) -> tuple[int, int] | None: ...

    async def mark_life_story(self, companion_ref: str, now: datetime) -> None: ...

    async def has_active_job(self) -> bool: ...

    async def count_recent(self, since: datetime) -> int: ...

    async def enqueue(
        self,
        *,
        companion_ref: str,
        locale: str,
        trigger: str,
        trigger_key: str,
        now: datetime,
        replaces_story_id: int | None = None,
    ) -> int | None: ...

    async def get_job(self, job_id: int) -> CompanionStoryJobModel | None: ...

    async def job_status(self, job_id: int) -> str | None: ...

    async def finish_job(
        self,
        job_id: int,
        *,
        status: str,
        now: datetime,
        skip_reason: str | None = None,
        error_code: str | None = None,
    ) -> None: ...

    async def requeue_job(self, job_id: int, *, not_before: datetime, error_code: str) -> None: ...

    async def story_for_job(self, job_id: int) -> CompanionGeneratedStoryModel | None: ...

    async def add_story(self, values: dict[str, Any]) -> CompanionGeneratedStoryModel | None: ...

    async def set_fragment_key(self, story: CompanionGeneratedStoryModel, key: str) -> None: ...

    async def used_source_ids(self) -> tuple[frozenset[int], frozenset[int]]: ...


class LifeStoryJobQueueProtocol(Protocol):
    """Cross-account claim and recovery for the worker's maintenance session."""

    async def settle_cancellations(self, now: datetime) -> int: ...

    async def recover_stale(self, now: datetime, max_attempts: int) -> int: ...

    async def claim(self, now: datetime, lease: timedelta) -> tuple[int, int, str] | None: ...


__all__ = [
    "GeneratedStoryRowProtocol",
    "GeneratedStorySourceProtocol",
    "LifeStoryGeneration",
    "LifeStoryJobQueueProtocol",
    "LifeStoryMaterial",
    "LifeStoryMaterialRequest",
    "LifeStoryMaterialSelectorProtocol",
    "LifeStoryRepositoryProtocol",
    "LifeStoryTextGeneratorProtocol",
    "MaterialKind",
]
