"""SQLAlchemy persistence for companion stories and bonds.

The repository runs on an owner-scoped ``AsyncSession`` (``apsor_app`` with the
owner's RLS context). Every statement also filters by ``user_id``.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionStoryModel,
)


class CompanionStoryRepository:
    """Owner-scoped CRUD for story overrides and bonds."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def get_story(
        self,
        *,
        preset_id: str | None,
        companion_id: int | None,
        locale: str,
    ) -> CompanionStoryModel | None:
        statement = select(CompanionStoryModel).where(
            CompanionStoryModel.user_id == self.user_id,
            CompanionStoryModel.locale == locale,
        )
        if preset_id is not None:
            statement = statement.where(CompanionStoryModel.preset_id == preset_id)
        else:
            statement = statement.where(CompanionStoryModel.companion_id == companion_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_custom_stories(self, companion_id: int) -> list[CompanionStoryModel]:
        statement = (
            select(CompanionStoryModel)
            .where(
                CompanionStoryModel.user_id == self.user_id,
                CompanionStoryModel.companion_id == companion_id,
            )
            .order_by(CompanionStoryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def add_story(
        self,
        *,
        preset_id: str | None,
        companion_id: int | None,
        locale: str,
        now: datetime,
    ) -> CompanionStoryModel:
        story = CompanionStoryModel(
            user_id=self.user_id,
            preset_id=preset_id,
            companion_id=companion_id,
            locale=locale,
            persona=None,
            lore_customized=False,
            created_at=now,
            updated_at=now,
        )
        self.session.add(story)
        await self.session.flush()
        return story

    async def delete_story(self, story: CompanionStoryModel) -> None:
        await self.session.delete(story)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def list_fragments(self, story_id: int) -> list[CompanionLoreFragmentModel]:
        statement = (
            select(CompanionLoreFragmentModel)
            .where(
                CompanionLoreFragmentModel.user_id == self.user_id,
                CompanionLoreFragmentModel.story_id == story_id,
            )
            .order_by(CompanionLoreFragmentModel.position, CompanionLoreFragmentModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_fragments(self, story_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(CompanionLoreFragmentModel)
            .where(
                CompanionLoreFragmentModel.user_id == self.user_id,
                CompanionLoreFragmentModel.story_id == story_id,
            )
        )
        return int((await self.session.execute(statement)).scalar_one())

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
    ) -> CompanionLoreFragmentModel:
        fragment = CompanionLoreFragmentModel(
            user_id=self.user_id,
            story_id=story_id,
            fragment_key=fragment_key,
            text=text,
            themes=list(themes),
            tier=tier,
            position=position,
            edited=edited,
            created_at=now,
            updated_at=now,
        )
        self.session.add(fragment)
        await self.session.flush()
        return fragment

    async def delete_fragment(self, fragment: CompanionLoreFragmentModel) -> None:
        await self.session.delete(fragment)
        await self.session.flush()

    async def delete_fragments(self, story_id: int) -> None:
        await self.session.execute(
            delete(CompanionLoreFragmentModel).where(
                CompanionLoreFragmentModel.user_id == self.user_id,
                CompanionLoreFragmentModel.story_id == story_id,
            )
        )

    async def get_bond(self, companion_ref: str) -> CompanionBondModel | None:
        statement = select(CompanionBondModel).where(
            CompanionBondModel.user_id == self.user_id,
            CompanionBondModel.companion_ref == companion_ref,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def increment_bond(self, companion_ref: str, now: datetime) -> CompanionBondModel:
        """Add one completed run atomically and return the updated bond."""
        statement = (
            insert(CompanionBondModel)
            .values(
                user_id=self.user_id,
                companion_ref=companion_ref,
                completed_runs=1,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[CompanionBondModel.user_id, CompanionBondModel.companion_ref],
                set_={
                    "completed_runs": CompanionBondModel.completed_runs + 1,
                    "updated_at": now,
                },
            )
            .returning(CompanionBondModel)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def clear_companion_ref(self, companion_ref: str) -> None:
        """Delete the bond row for a companion that no longer exists."""
        await self.session.execute(
            delete(CompanionBondModel).where(
                CompanionBondModel.user_id == self.user_id,
                CompanionBondModel.companion_ref == companion_ref,
            )
        )


__all__ = ["CompanionStoryRepository"]
