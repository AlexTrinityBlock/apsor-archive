"""Store protocol for the root companion administration service."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.module.companion.model.companion_admin_model import (
    CompanionAccountPolicyModel,
    CompanionAdminAccessLogModel,
    CompanionAdminLoreOverrideModel,
    CompanionAdminStoryOverrideModel,
    CompanionUserConfigModel,
)
from app.module.companion.model.companion_life_story_model import (
    CompanionGeneratedStoryModel,
    CompanionStoryJobModel,
)
from app.module.companion.model.companion_model import CompanionModel, CompanionPreferenceModel
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionLoreToldModel,
    CompanionStoryModel,
)
from app.module.companion.model.companion_world_model import (
    CompanionCanonEntityModel,
    CompanionConfigModel,
    CompanionLoreItemModel,
    CompanionLoreItemTextModel,
    CompanionPresetModel,
    CompanionPresetTextModel,
    CompanionPromptTemplateModel,
    CompanionSeedStateModel,
    CompanionWorldDocModel,
    CompanionWorldDocRevisionModel,
)


@dataclass(frozen=True)
class AccountRow:
    """The account columns the companion admin views need."""

    id: int
    username: str
    display_name: str | None
    role: str
    is_active: bool


class CompanionAdminStoreProtocol(Protocol):
    """Cross-account companion persistence under the admin scope."""

    async def add(self, row: object) -> None: ...

    async def delete(self, row: object) -> None: ...

    async def flush(self) -> None: ...

    async def list_accounts(self) -> list[AccountRow]: ...

    async def get_account(self, user_id: int) -> AccountRow | None: ...

    async def list_presets(self) -> list[CompanionPresetModel]: ...

    async def get_preset(self, preset_id: str) -> CompanionPresetModel | None: ...

    async def clear_global_default(self, except_id: str) -> None: ...

    async def list_preset_texts(
        self, preset_id: str | None = None
    ) -> list[CompanionPresetTextModel]: ...

    async def get_preset_text(
        self, preset_id: str, locale: str
    ) -> CompanionPresetTextModel | None: ...

    async def list_lore_items(
        self, preset_id: str | None = None
    ) -> list[CompanionLoreItemModel]: ...

    async def get_lore_item(self, item_id: int) -> CompanionLoreItemModel | None: ...

    async def find_lore_item(
        self, preset_id: str, fragment_key: str
    ) -> CompanionLoreItemModel | None: ...

    async def list_lore_texts(
        self, item_ids: Sequence[int]
    ) -> list[CompanionLoreItemTextModel]: ...

    async def get_lore_text(
        self, item_id: int, locale: str
    ) -> CompanionLoreItemTextModel | None: ...

    async def list_world_docs(self) -> list[CompanionWorldDocModel]: ...

    async def get_world_doc(self, doc_key: str, locale: str) -> CompanionWorldDocModel | None: ...

    async def list_doc_revisions(
        self, doc_key: str, locale: str
    ) -> list[CompanionWorldDocRevisionModel]: ...

    async def list_canon(self, locale: str | None = None) -> list[CompanionCanonEntityModel]: ...

    async def get_canon(self, entity_id: str, locale: str) -> CompanionCanonEntityModel | None: ...

    async def get_config(self) -> CompanionConfigModel | None: ...

    async def list_templates(self) -> list[CompanionPromptTemplateModel]: ...

    async def get_template(self, key: str, locale: str) -> CompanionPromptTemplateModel | None: ...

    async def get_seed_state(self) -> CompanionSeedStateModel | None: ...

    async def bump_content_version(self) -> None: ...

    async def count_seed_flags(self) -> tuple[int, int]: ...

    async def get_policy(self, user_id: int) -> CompanionAccountPolicyModel | None: ...

    async def get_user_config(self, user_id: int) -> CompanionUserConfigModel | None: ...

    async def list_preferences(self) -> list[CompanionPreferenceModel]: ...

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None: ...

    async def list_custom_companions(self, user_id: int) -> list[CompanionModel]: ...

    async def list_bonds(self, user_id: int | None = None) -> list[CompanionBondModel]: ...

    async def get_bond(self, user_id: int, companion_ref: str) -> CompanionBondModel | None: ...

    async def list_told(
        self, user_id: int | None = None, companion_ref: str | None = None
    ) -> list[CompanionLoreToldModel]: ...

    async def delete_told(
        self, user_id: int, companion_ref: str, fragment_key: str | None = None
    ) -> None: ...

    async def get_told(
        self, user_id: int, companion_ref: str, fragment_key: str
    ) -> CompanionLoreToldModel | None: ...

    async def get_user_story(
        self, user_id: int, *, preset_id: str | None, companion_id: int | None, locale: str
    ) -> CompanionStoryModel | None: ...

    async def list_user_fragments(
        self, user_id: int, story_id: int
    ) -> list[CompanionLoreFragmentModel]: ...

    async def get_persona_override(
        self, user_id: int, companion_ref: str, locale: str
    ) -> CompanionAdminStoryOverrideModel | None: ...

    async def list_lore_overrides(
        self, user_id: int, companion_ref: str, locale: str
    ) -> list[CompanionAdminLoreOverrideModel]: ...

    async def get_lore_override(
        self, user_id: int, companion_ref: str, locale: str, fragment_key: str
    ) -> CompanionAdminLoreOverrideModel | None: ...

    async def list_generated(
        self, user_id: int | None = None, companion_ref: str | None = None
    ) -> list[CompanionGeneratedStoryModel]: ...

    async def get_generated(
        self, user_id: int, story_id: int
    ) -> CompanionGeneratedStoryModel | None: ...

    async def list_jobs(self, user_id: int, limit: int = 50) -> list[CompanionStoryJobModel]: ...

    async def get_job(self, user_id: int, job_id: int) -> CompanionStoryJobModel | None: ...

    async def active_job(
        self, user_id: int, companion_ref: str
    ) -> CompanionStoryJobModel | None: ...

    async def log_access(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        action: str,
        story_id: int | None = None,
        companion_ref: str | None = None,
        at: datetime | None = None,
    ) -> None: ...

    async def list_access(
        self, target_user_id: int, limit: int = 100
    ) -> list[CompanionAdminAccessLogModel]: ...


class CompanionSeederProtocol(Protocol):
    """Applies the shipped seed bundle (provided by the foundation seeder)."""

    async def apply(self, *, force_keys: Sequence[str] = ()) -> None: ...


__all__ = ["AccountRow", "CompanionAdminStoreProtocol", "CompanionSeederProtocol"]
