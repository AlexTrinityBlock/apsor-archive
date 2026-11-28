"""Ports the life-story worker depends on.

A life story is written by the account's own assigned model from a bounded set
of the account's own memories plus the world canon. The worker reaches the
archive only through :class:`LifeStoryMaterialSelectorProtocol` (implemented
in ``companion/dependencies.py`` over the knowledge slice, inside the owner's
RLS session) and the model only through :class:`LifeStoryTextGeneratorProtocol`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

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


__all__ = [
    "LifeStoryGeneration",
    "LifeStoryMaterial",
    "LifeStoryMaterialRequest",
    "LifeStoryMaterialSelectorProtocol",
    "LifeStoryTextGeneratorProtocol",
    "MaterialKind",
]
