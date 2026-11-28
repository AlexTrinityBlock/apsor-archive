"""Ports the companion story service and lore recall depend on."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.companion.model.companion_model import (
    CompanionModel,
    CompanionPreferenceModel,
)
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionStoryModel,
)


class CompanionStoryRepositoryProtocol(Protocol):
    """Owner-scoped persistence for story overrides and bonds."""

    async def get_story(
        self,
        *,
        preset_id: str | None,
        companion_id: int | None,
        locale: str,
    ) -> CompanionStoryModel | None: ...

    async def list_custom_stories(self, companion_id: int) -> list[CompanionStoryModel]: ...

    async def add_story(
        self,
        *,
        preset_id: str | None,
        companion_id: int | None,
        locale: str,
        now: datetime,
    ) -> CompanionStoryModel: ...

    async def delete_story(self, story: CompanionStoryModel) -> None: ...

    async def flush(self) -> None: ...

    async def list_fragments(self, story_id: int) -> list[CompanionLoreFragmentModel]: ...

    async def count_fragments(self, story_id: int) -> int: ...

    async def add_fragment(
        self,
        *,
        story_id: int,
        fragment_key: str,
        text: str,
        themes: Sequence[str],
        tier: str,
        position: int,
        edited: bool,
        now: datetime,
    ) -> CompanionLoreFragmentModel: ...

    async def delete_fragment(self, fragment: CompanionLoreFragmentModel) -> None: ...

    async def delete_fragments(self, story_id: int) -> None: ...

    async def get_bond(self, companion_ref: str) -> CompanionBondModel | None: ...

    async def increment_bond(self, companion_ref: str, now: datetime) -> CompanionBondModel: ...

    async def clear_companion_ref(self, companion_ref: str) -> None: ...


class CompanionLookupProtocol(Protocol):
    """The slice's companion and preference reads the story service needs."""

    async def get_companion(
        self,
        user_id: int,
        companion_id: int,
    ) -> CompanionModel | None: ...

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None: ...


class LoreEmbedderProtocol(Protocol):
    """Turn text batches into L2-normalized vectors (the account's embedder)."""

    dimension: int
    model_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class LoreEmbeddingQuotaProtocol(Protocol):
    """The account's embedding allowance."""

    async def embedding_allowed(self, characters: int) -> bool: ...

    async def record_embedding(self, characters: int) -> None: ...


__all__ = [
    "CompanionLookupProtocol",
    "CompanionStoryRepositoryProtocol",
    "LoreEmbedderProtocol",
    "LoreEmbeddingQuotaProtocol",
]
