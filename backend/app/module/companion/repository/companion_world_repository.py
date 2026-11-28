"""Reads of the global companion world content and root's per-account settings.

The global tables are read-all (``{table}_read``), so any ``apsor_app``
transaction may read them. ``companion_user_config`` and
``companion_account_policy`` are ``_owner_read``: read them in the account's own
session. Writes belong to the seeder and to root administration.
"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.companion.domain.seed_domain import CONFIG_COLUMNS, SEED_BUNDLE
from app.module.companion.model.companion_admin_model import (
    CompanionAccountPolicyModel,
    CompanionUserConfigModel,
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
)


class CompanionWorldRepository:
    """Global world content and root's per-account companion settings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- versions ----------------------------------------------------------

    async def content_version(self) -> int:
        """Return the live content version (0 before the first seed)."""
        value = await self.session.scalar(
            select(CompanionSeedStateModel.content_version).where(
                CompanionSeedStateModel.bundle == SEED_BUNDLE
            )
        )
        return int(value or 0)

    async def bump_content_version(self) -> int:
        """Increment the content version after an edit; return the new value.

        Root administration calls this after any write to presets, lore,
        canon, or world documents so every process reloads its cache.
        """
        result = await self.session.execute(
            update(CompanionSeedStateModel)
            .where(CompanionSeedStateModel.bundle == SEED_BUNDLE)
            .values(content_version=CompanionSeedStateModel.content_version + 1)
            .returning(CompanionSeedStateModel.content_version)
        )
        return int(result.scalar_one_or_none() or 0)

    # --- content -----------------------------------------------------------

    async def list_presets(self) -> list[CompanionPresetModel]:
        return list(
            (
                await self.session.scalars(
                    select(CompanionPresetModel).order_by(
                        CompanionPresetModel.position,
                        CompanionPresetModel.id,
                    )
                )
            ).all()
        )

    async def list_preset_texts(self) -> list[CompanionPresetTextModel]:
        return list((await self.session.scalars(select(CompanionPresetTextModel))).all())

    async def list_lore_items(self) -> list[CompanionLoreItemModel]:
        return list(
            (
                await self.session.scalars(
                    select(CompanionLoreItemModel)
                    .where(CompanionLoreItemModel.retired_at.is_(None))
                    .order_by(
                        CompanionLoreItemModel.preset_id,
                        CompanionLoreItemModel.position,
                        CompanionLoreItemModel.id,
                    )
                )
            ).all()
        )

    async def list_lore_item_texts(self) -> list[CompanionLoreItemTextModel]:
        return list((await self.session.scalars(select(CompanionLoreItemTextModel))).all())

    async def list_canon(self, locales: tuple[str, ...]) -> list[CompanionCanonEntityModel]:
        return list(
            (
                await self.session.scalars(
                    select(CompanionCanonEntityModel).where(
                        CompanionCanonEntityModel.locale.in_(locales)
                    )
                )
            ).all()
        )

    async def get_world_doc(self, doc_key: str, locale: str) -> CompanionWorldDocModel | None:
        return await self.session.get(CompanionWorldDocModel, (doc_key, locale))

    # --- configuration -----------------------------------------------------

    async def get_config(self) -> CompanionConfigModel | None:
        return await self.session.get(CompanionConfigModel, 1)

    async def list_templates(self) -> list[CompanionPromptTemplateModel]:
        return list((await self.session.scalars(select(CompanionPromptTemplateModel))).all())

    async def get_user_config(self, user_id: int) -> CompanionUserConfigModel | None:
        return await self.session.get(CompanionUserConfigModel, user_id)

    async def get_account_policy(self, user_id: int) -> CompanionAccountPolicyModel | None:
        return await self.session.get(CompanionAccountPolicyModel, user_id)


def config_values(model: CompanionConfigModel) -> dict[str, Any]:
    """Return the tunable columns of the config singleton as a plain dict."""
    return {name: getattr(model, name) for name in CONFIG_COLUMNS}


__all__ = ["CompanionWorldRepository", "config_values"]
