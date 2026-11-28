"""Persistence for the root companion administration surface.

The session must already carry ``app.user_role = 'root'`` and
``app.admin_scope = 'companion'`` (see ``apply_admin_scope``). Row-level
security then exposes companion tables across accounts — and nothing else: the
archive (``memory``, ``file``, ``chunk``) stays owner-only. Every per-account
statement still filters by ``user_id`` explicitly.

``app_user`` sits outside RLS and belongs to the auth slice, so it is read with
plain SQL rather than by importing that slice's model.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.module.companion.protocol.companion_admin_protocol import AccountRow
from app.module.companion.repository.companion_world_repository import (
    CompanionWorldRepository,
)

_SEED_TRACKED = (
    CompanionPresetModel,
    CompanionPresetTextModel,
    CompanionLoreItemModel,
    CompanionLoreItemTextModel,
    CompanionCanonEntityModel,
    CompanionWorldDocModel,
    CompanionPromptTemplateModel,
)


class CompanionAdminRepository:
    """Cross-account companion reads and writes under the admin scope."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- generic -----------------------------------------------------------

    async def add(self, row: object) -> None:
        self.session.add(row)
        await self.session.flush()

    async def delete(self, row: object) -> None:
        await self.session.delete(row)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def _all[RowT](self, statement: Select[RowT]) -> list[RowT]:
        return list((await self.session.execute(statement)).scalars().all())

    # --- accounts ----------------------------------------------------------

    async def list_accounts(self) -> list[AccountRow]:
        rows = await self.session.execute(
            text(
                "SELECT id, username, display_name, role, is_active FROM app_user "
                "ORDER BY role = 'root' DESC, lower(username)"
            )
        )
        return [AccountRow(*row) for row in rows.all()]

    async def get_account(self, user_id: int) -> AccountRow | None:
        row = (
            await self.session.execute(
                text(
                    "SELECT id, username, display_name, role, is_active FROM app_user "
                    "WHERE id = :user_id"
                ),
                {"user_id": user_id},
            )
        ).first()
        return AccountRow(*row) if row is not None else None

    # --- global content ----------------------------------------------------

    async def list_presets(self) -> list[CompanionPresetModel]:
        return await self._all(
            select(CompanionPresetModel).order_by(
                CompanionPresetModel.position, CompanionPresetModel.id
            )
        )

    async def get_preset(self, preset_id: str) -> CompanionPresetModel | None:
        return await self.session.get(CompanionPresetModel, preset_id)

    async def clear_global_default(self, except_id: str) -> None:
        for preset in await self.list_presets():
            if preset.id != except_id and preset.is_global_default:
                preset.is_global_default = False
        await self.session.flush()

    async def list_preset_texts(
        self, preset_id: str | None = None
    ) -> list[CompanionPresetTextModel]:
        statement = select(CompanionPresetTextModel)
        if preset_id is not None:
            statement = statement.where(CompanionPresetTextModel.preset_id == preset_id)
        return await self._all(statement)

    async def get_preset_text(self, preset_id: str, locale: str) -> CompanionPresetTextModel | None:
        return await self.session.get(CompanionPresetTextModel, (preset_id, locale))

    async def list_lore_items(self, preset_id: str | None = None) -> list[CompanionLoreItemModel]:
        statement = select(CompanionLoreItemModel)
        if preset_id is not None:
            statement = statement.where(CompanionLoreItemModel.preset_id == preset_id)
        return await self._all(
            statement.order_by(
                CompanionLoreItemModel.preset_id,
                CompanionLoreItemModel.position,
                CompanionLoreItemModel.fragment_key,
            )
        )

    async def get_lore_item(self, item_id: int) -> CompanionLoreItemModel | None:
        return await self.session.get(CompanionLoreItemModel, item_id)

    async def find_lore_item(
        self, preset_id: str, fragment_key: str
    ) -> CompanionLoreItemModel | None:
        statement = select(CompanionLoreItemModel).where(
            CompanionLoreItemModel.preset_id == preset_id,
            CompanionLoreItemModel.fragment_key == fragment_key,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_lore_texts(self, item_ids: Sequence[int]) -> list[CompanionLoreItemTextModel]:
        if not item_ids:
            return []
        return await self._all(
            select(CompanionLoreItemTextModel).where(
                CompanionLoreItemTextModel.item_id.in_(list(item_ids))
            )
        )

    async def get_lore_text(self, item_id: int, locale: str) -> CompanionLoreItemTextModel | None:
        return await self.session.get(CompanionLoreItemTextModel, (item_id, locale))

    async def list_world_docs(self) -> list[CompanionWorldDocModel]:
        return await self._all(
            select(CompanionWorldDocModel).order_by(
                CompanionWorldDocModel.doc_key, CompanionWorldDocModel.locale
            )
        )

    async def get_world_doc(self, doc_key: str, locale: str) -> CompanionWorldDocModel | None:
        return await self.session.get(CompanionWorldDocModel, (doc_key, locale))

    async def list_doc_revisions(
        self, doc_key: str, locale: str
    ) -> list[CompanionWorldDocRevisionModel]:
        return await self._all(
            select(CompanionWorldDocRevisionModel)
            .where(
                CompanionWorldDocRevisionModel.doc_key == doc_key,
                CompanionWorldDocRevisionModel.locale == locale,
            )
            .order_by(CompanionWorldDocRevisionModel.version.desc())
        )

    async def list_canon(self, locale: str | None = None) -> list[CompanionCanonEntityModel]:
        statement = select(CompanionCanonEntityModel)
        if locale is not None:
            statement = statement.where(CompanionCanonEntityModel.locale == locale)
        return await self._all(statement.order_by(CompanionCanonEntityModel.entity_id))

    async def get_canon(self, entity_id: str, locale: str) -> CompanionCanonEntityModel | None:
        return await self.session.get(CompanionCanonEntityModel, (entity_id, locale))

    async def get_config(self) -> CompanionConfigModel | None:
        return await self.session.get(CompanionConfigModel, 1)

    async def list_templates(self) -> list[CompanionPromptTemplateModel]:
        return await self._all(
            select(CompanionPromptTemplateModel).order_by(
                CompanionPromptTemplateModel.template_key, CompanionPromptTemplateModel.locale
            )
        )

    async def get_template(self, key: str, locale: str) -> CompanionPromptTemplateModel | None:
        return await self.session.get(CompanionPromptTemplateModel, (key, locale))

    async def get_seed_state(self) -> CompanionSeedStateModel | None:
        return (
            await self.session.execute(select(CompanionSeedStateModel).limit(1))
        ).scalar_one_or_none()

    async def bump_content_version(self) -> None:
        """Bump the content version through the one shared implementation."""
        await CompanionWorldRepository(self.session).bump_content_version()

    async def count_seed_flags(self) -> tuple[int, int]:
        """Return (admin-modified rows, rows whose shipped seed changed under an edit)."""
        modified = 0
        upstream = 0
        for model in _SEED_TRACKED:
            modified += int(
                (
                    await self.session.execute(
                        select(func.count()).select_from(model).where(model.admin_modified)
                    )
                ).scalar_one()
            )
            upstream += int(
                (
                    await self.session.execute(
                        select(func.count())
                        .select_from(model)
                        .where(
                            model.upstream_seed_hash.is_not(None),
                            model.upstream_seed_hash != model.seed_hash,
                        )
                    )
                ).scalar_one()
            )
        return modified, upstream

    # --- per account -------------------------------------------------------

    async def get_policy(self, user_id: int) -> CompanionAccountPolicyModel | None:
        return await self.session.get(CompanionAccountPolicyModel, user_id)

    async def get_user_config(self, user_id: int) -> CompanionUserConfigModel | None:
        return await self.session.get(CompanionUserConfigModel, user_id)

    async def list_preferences(self) -> list[CompanionPreferenceModel]:
        return await self._all(select(CompanionPreferenceModel))

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None:
        return (
            await self.session.execute(
                select(CompanionPreferenceModel).where(CompanionPreferenceModel.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def list_custom_companions(self, user_id: int) -> list[CompanionModel]:
        return await self._all(
            select(CompanionModel)
            .where(CompanionModel.user_id == user_id)
            .order_by(CompanionModel.id)
        )

    async def list_bonds(self, user_id: int | None = None) -> list[CompanionBondModel]:
        statement = select(CompanionBondModel)
        if user_id is not None:
            statement = statement.where(CompanionBondModel.user_id == user_id)
        return await self._all(statement.order_by(CompanionBondModel.companion_ref))

    async def get_bond(self, user_id: int, companion_ref: str) -> CompanionBondModel | None:
        return await self.session.get(CompanionBondModel, (user_id, companion_ref))

    async def list_told(
        self, user_id: int | None = None, companion_ref: str | None = None
    ) -> list[CompanionLoreToldModel]:
        statement = select(CompanionLoreToldModel)
        if user_id is not None:
            statement = statement.where(CompanionLoreToldModel.user_id == user_id)
        if companion_ref is not None:
            statement = statement.where(CompanionLoreToldModel.companion_ref == companion_ref)
        return await self._all(statement)

    async def delete_told(
        self, user_id: int, companion_ref: str, fragment_key: str | None = None
    ) -> None:
        statement = delete(CompanionLoreToldModel).where(
            CompanionLoreToldModel.user_id == user_id,
            CompanionLoreToldModel.companion_ref == companion_ref,
        )
        if fragment_key is not None:
            statement = statement.where(CompanionLoreToldModel.fragment_key == fragment_key)
        await self.session.execute(statement)
        await self.session.flush()

    async def get_told(
        self, user_id: int, companion_ref: str, fragment_key: str
    ) -> CompanionLoreToldModel | None:
        return await self.session.get(
            CompanionLoreToldModel, (user_id, companion_ref, fragment_key)
        )

    async def get_user_story(
        self, user_id: int, *, preset_id: str | None, companion_id: int | None, locale: str
    ) -> CompanionStoryModel | None:
        statement = select(CompanionStoryModel).where(
            CompanionStoryModel.user_id == user_id,
            CompanionStoryModel.locale == locale,
        )
        if preset_id is not None:
            statement = statement.where(CompanionStoryModel.preset_id == preset_id)
        else:
            statement = statement.where(CompanionStoryModel.companion_id == companion_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_user_fragments(
        self, user_id: int, story_id: int
    ) -> list[CompanionLoreFragmentModel]:
        return await self._all(
            select(CompanionLoreFragmentModel)
            .where(
                CompanionLoreFragmentModel.user_id == user_id,
                CompanionLoreFragmentModel.story_id == story_id,
            )
            .order_by(CompanionLoreFragmentModel.position)
        )

    async def get_persona_override(
        self, user_id: int, companion_ref: str, locale: str
    ) -> CompanionAdminStoryOverrideModel | None:
        return await self.session.get(
            CompanionAdminStoryOverrideModel, (user_id, companion_ref, locale)
        )

    async def list_lore_overrides(
        self, user_id: int, companion_ref: str, locale: str
    ) -> list[CompanionAdminLoreOverrideModel]:
        return await self._all(
            select(CompanionAdminLoreOverrideModel)
            .where(
                CompanionAdminLoreOverrideModel.user_id == user_id,
                CompanionAdminLoreOverrideModel.companion_ref == companion_ref,
                CompanionAdminLoreOverrideModel.locale == locale,
            )
            .order_by(CompanionAdminLoreOverrideModel.fragment_key)
        )

    async def get_lore_override(
        self, user_id: int, companion_ref: str, locale: str, fragment_key: str
    ) -> CompanionAdminLoreOverrideModel | None:
        return await self.session.get(
            CompanionAdminLoreOverrideModel, (user_id, companion_ref, locale, fragment_key)
        )

    async def list_generated(
        self, user_id: int | None = None, companion_ref: str | None = None
    ) -> list[CompanionGeneratedStoryModel]:
        statement = select(CompanionGeneratedStoryModel)
        if user_id is not None:
            statement = statement.where(CompanionGeneratedStoryModel.user_id == user_id)
        if companion_ref is not None:
            statement = statement.where(CompanionGeneratedStoryModel.companion_ref == companion_ref)
        return await self._all(statement.order_by(CompanionGeneratedStoryModel.id.desc()))

    async def get_generated(
        self, user_id: int, story_id: int
    ) -> CompanionGeneratedStoryModel | None:
        story = await self.session.get(CompanionGeneratedStoryModel, story_id)
        return story if story is not None and story.user_id == user_id else None

    async def list_jobs(self, user_id: int, limit: int = 50) -> list[CompanionStoryJobModel]:
        return await self._all(
            select(CompanionStoryJobModel)
            .where(CompanionStoryJobModel.user_id == user_id)
            .order_by(CompanionStoryJobModel.id.desc())
            .limit(limit)
        )

    async def get_job(self, user_id: int, job_id: int) -> CompanionStoryJobModel | None:
        job = await self.session.get(CompanionStoryJobModel, job_id)
        return job if job is not None and job.user_id == user_id else None

    async def active_job(self, user_id: int, companion_ref: str) -> CompanionStoryJobModel | None:
        return (
            await self.session.execute(
                select(CompanionStoryJobModel)
                .where(
                    CompanionStoryJobModel.user_id == user_id,
                    CompanionStoryJobModel.companion_ref == companion_ref,
                    CompanionStoryJobModel.status.in_(("queued", "running", "cancel_requested")),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def log_access(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        action: str,
        story_id: int | None = None,
        companion_ref: str | None = None,
        at: datetime | None = None,
    ) -> None:
        row = CompanionAdminAccessLogModel(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action=action,
            story_id=story_id,
            companion_ref=companion_ref,
        )
        if at is not None:
            row.at = at
        self.session.add(row)
        await self.session.flush()

    async def list_access(
        self, target_user_id: int, limit: int = 100
    ) -> list[CompanionAdminAccessLogModel]:
        return await self._all(
            select(CompanionAdminAccessLogModel)
            .where(CompanionAdminAccessLogModel.target_user_id == target_user_id)
            .order_by(CompanionAdminAccessLogModel.id.desc())
            .limit(limit)
        )


__all__ = ["AccountRow", "CompanionAdminRepository"]
