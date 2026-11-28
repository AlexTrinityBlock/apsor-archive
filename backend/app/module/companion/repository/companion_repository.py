"""SQLAlchemy persistence for custom companions and the preference.

The repository runs on the request-scoped ``AsyncSession`` (``apsor_app`` with
the owner's RLS context). Every statement also filters by ``user_id`` so the
application filter and the database policy enforce the same ownership rule.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.companion.model.companion_model import (
    CompanionFrameModel,
    CompanionModel,
    CompanionPreferenceModel,
)


class CompanionRepository:
    """Request-transaction CRUD for one owner's companions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_companions(self, user_id: int) -> list[CompanionModel]:
        statement = (
            select(CompanionModel)
            .where(CompanionModel.user_id == user_id)
            .order_by(CompanionModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_companions(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(CompanionModel)
            .where(CompanionModel.user_id == user_id)
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def get_companion(self, user_id: int, companion_id: int) -> CompanionModel | None:
        statement = select(CompanionModel).where(
            CompanionModel.id == companion_id,
            CompanionModel.user_id == user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add_companion(
        self,
        *,
        user_id: int,
        name: str,
        gender: str | None,
        now: datetime,
    ) -> CompanionModel:
        companion = CompanionModel(
            user_id=user_id,
            name=name,
            gender=gender,
            created_at=now,
            updated_at=now,
        )
        self.session.add(companion)
        await self.session.flush()
        return companion

    async def touch_companion(self, companion: CompanionModel, now: datetime) -> None:
        companion.updated_at = now
        await self.session.flush()

    async def delete_companion(self, companion: CompanionModel) -> None:
        await self.session.delete(companion)
        await self.session.flush()

    async def list_frames(
        self,
        user_id: int,
        companion_ids: Sequence[int],
    ) -> list[CompanionFrameModel]:
        if not companion_ids:
            return []
        statement = (
            select(CompanionFrameModel)
            .where(
                CompanionFrameModel.user_id == user_id,
                CompanionFrameModel.companion_id.in_(list(companion_ids)),
            )
            .order_by(
                CompanionFrameModel.companion_id,
                CompanionFrameModel.action,
                CompanionFrameModel.position,
                CompanionFrameModel.id,
            )
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_frame(
        self,
        user_id: int,
        companion_id: int,
        frame_id: int,
    ) -> CompanionFrameModel | None:
        statement = select(CompanionFrameModel).where(
            CompanionFrameModel.id == frame_id,
            CompanionFrameModel.companion_id == companion_id,
            CompanionFrameModel.user_id == user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add_frame(
        self,
        *,
        user_id: int,
        companion_id: int,
        action: str,
        position: int,
        storage_backend: str,
        storage_key: str,
        mime_type: str,
        width: int,
        height: int,
        size_bytes: int,
        sha256: str,
        now: datetime,
    ) -> CompanionFrameModel:
        frame = CompanionFrameModel(
            user_id=user_id,
            companion_id=companion_id,
            action=action,
            position=position,
            storage_backend=storage_backend,
            storage_key=storage_key,
            mime_type=mime_type,
            width=width,
            height=height,
            size_bytes=size_bytes,
            sha256=sha256,
            created_at=now,
        )
        self.session.add(frame)
        await self.session.flush()
        return frame

    async def delete_frame(self, frame: CompanionFrameModel) -> None:
        await self.session.delete(frame)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None:
        statement = select(CompanionPreferenceModel).where(
            CompanionPreferenceModel.user_id == user_id
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def upsert_preference(
        self,
        *,
        user_id: int,
        selected: str | None,
        enabled: bool,
        motion: str,
        size: str,
        opacity_mode: str,
        position_x: float | None,
        position_y: float | None,
        now: datetime,
    ) -> CompanionPreferenceModel:
        values = {
            "selected": selected,
            "enabled": enabled,
            "motion": motion,
            "size": size,
            "opacity_mode": opacity_mode,
            "position_x": position_x,
            "position_y": position_y,
            "updated_at": now,
        }
        statement = (
            insert(CompanionPreferenceModel)
            .values(user_id=user_id, **values)
            .on_conflict_do_update(
                index_elements=[CompanionPreferenceModel.user_id],
                set_=values,
            )
            .returning(CompanionPreferenceModel)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def clear_selection(self, user_id: int, selected: str, now: datetime) -> None:
        await self.session.execute(
            update(CompanionPreferenceModel)
            .where(
                CompanionPreferenceModel.user_id == user_id,
                CompanionPreferenceModel.selected == selected,
            )
            .values(selected=None, updated_at=now)
        )


__all__ = ["CompanionRepository"]
