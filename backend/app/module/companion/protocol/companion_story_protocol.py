"""Ports the companion story service and lore recall depend on."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.companion.domain.companion_policy_domain import AccountCompanionPolicy
from app.module.companion.domain.story_domain import (
    CanonEntry,
    CompanionRuntimeConfig,
    PresetStory,
    WorldDoc,
)
from app.module.companion.model.companion_admin_model import (
    CompanionAdminLoreOverrideModel,
)
from app.module.companion.model.companion_life_story_model import (
    CompanionGeneratedStoryModel,
)
from app.module.companion.model.companion_model import (
    CompanionModel,
    CompanionPreferenceModel,
)
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionLoreToldModel,
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
        weight: str,
        position: int,
        edited: bool,
        now: datetime,
    ) -> CompanionLoreFragmentModel: ...

    async def delete_fragment(self, fragment: CompanionLoreFragmentModel) -> None: ...

    async def delete_fragments(self, story_id: int) -> None: ...

    async def get_bond(self, companion_ref: str) -> CompanionBondModel | None: ...

    async def increment_bond(self, companion_ref: str, now: datetime) -> CompanionBondModel: ...

    async def set_last_story_run(self, companion_ref: str, run: int, now: datetime) -> None: ...

    async def list_told(self, companion_ref: str) -> list[CompanionLoreToldModel]: ...

    async def record_told(
        self,
        companion_ref: str,
        fragment_keys: list[str],
        source: str,
        now: datetime,
    ) -> None: ...

    async def clear_companion_ref(self, companion_ref: str) -> None: ...

    async def get_admin_persona(self, companion_ref: str, locale: str) -> str | None: ...

    async def list_admin_lore_overrides(
        self,
        companion_ref: str,
        locale: str,
    ) -> list[CompanionAdminLoreOverrideModel]: ...

    async def list_published_generated(
        self,
        companion_ref: str,
    ) -> list[CompanionGeneratedStoryModel]: ...


class CompanionLookupProtocol(Protocol):
    """The slice's companion and preference reads the story service needs."""

    async def get_companion(
        self,
        user_id: int,
        companion_id: int,
    ) -> CompanionModel | None: ...

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None: ...

    async def list_companions(self, user_id: int) -> list[CompanionModel]: ...


class CompanionStoryConfigProviderProtocol(Protocol):
    """Supply the live story tunables and templates (root-editable; seeded).

    ``user_id=None`` returns the global configuration; an account id overlays
    root's per-account overrides (``companion_user_config``).
    """

    async def load(self, user_id: int | None = None) -> CompanionRuntimeConfig: ...


class CompanionContentProviderProtocol(Protocol):
    """Supply preset stories, canon, and world documents (DB-backed; seeded)."""

    async def presets(self, locale: str) -> list[PresetStory]: ...

    async def preset(self, preset_id: str, locale: str) -> PresetStory | None: ...

    async def enabled_preset_ids(self) -> list[str]: ...

    async def global_default_preset_id(self) -> str: ...

    async def canon(self, locale: str) -> dict[str, CanonEntry]: ...

    async def world_doc(self, doc_key: str, locale: str) -> WorldDoc | None: ...

    async def content_version(self) -> int: ...


class CompanionPolicyProviderProtocol(Protocol):
    """Supply root's companion policy for one account (defaults when unset)."""

    async def load(self, user_id: int) -> AccountCompanionPolicy: ...


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
    "CompanionContentProviderProtocol",
    "CompanionLookupProtocol",
    "CompanionPolicyProviderProtocol",
    "CompanionStoryConfigProviderProtocol",
    "CompanionStoryRepositoryProtocol",
    "LoreEmbedderProtocol",
    "LoreEmbeddingQuotaProtocol",
]
