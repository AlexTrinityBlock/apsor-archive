"""SQLAlchemy persistence for memories."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, any_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.memory_model import (
    MEMORY_ACTIVE,
    MEMORY_DEPRECATED,
    MemoryModel,
)
from app.module.knowledge.model.summary_model import MemorySummaryModel
from app.shared.time import utcnow


class MemoryRepository:
    """Queries over the linear memory timeline."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, memory: MemoryModel) -> MemoryModel:
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def get_by_id(self, memory_id: int) -> MemoryModel | None:
        return await self.session.get(MemoryModel, memory_id)

    async def save(self, memory: MemoryModel) -> MemoryModel:
        """Flush an edited memory and stamp its update time."""
        memory.updated_at = utcnow()
        await self.session.flush()
        return memory

    async def list_by_ids(self, memory_ids: Sequence[int]) -> list[MemoryModel]:
        if not memory_ids:
            return []
        statement = select(MemoryModel).where(MemoryModel.id.in_(memory_ids))
        return list((await self.session.execute(statement)).scalars().all())

    async def deprecate(
        self,
        memory: MemoryModel,
        successor_id: int | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        """Retire a memory, with or without a successor.

        Both paths stamp ``deprecated_at`` so the ledger records when the record
        left the active tip; only a replacement sets ``superseded_by_id``.
        """
        now = utcnow()
        memory.status = MEMORY_DEPRECATED
        if successor_id is not None:
            memory.superseded_by_id = successor_id
        memory.deprecated_at = now
        memory.deprecated_reason = reason
        memory.updated_at = now
        await self.session.flush()

    async def list_neighbors(
        self,
        target: MemoryModel,
        *,
        before: int,
        after: int,
    ) -> tuple[list[MemoryModel], list[MemoryModel]]:
        previous_statement = (
            select(MemoryModel)
            .where(
                MemoryModel.deleted_at.is_(None),
                or_(
                    MemoryModel.memory_time < target.memory_time,
                    and_(
                        MemoryModel.memory_time == target.memory_time,
                        MemoryModel.id < target.id,
                    ),
                ),
            )
            .order_by(MemoryModel.memory_time.desc(), MemoryModel.id.desc())
            .limit(before)
        )
        next_statement = (
            select(MemoryModel)
            .where(
                MemoryModel.deleted_at.is_(None),
                or_(
                    MemoryModel.memory_time > target.memory_time,
                    and_(
                        MemoryModel.memory_time == target.memory_time,
                        MemoryModel.id > target.id,
                    ),
                ),
            )
            .order_by(MemoryModel.memory_time, MemoryModel.id)
            .limit(after)
        )
        previous = list((await self.session.execute(previous_statement)).scalars().all())
        previous.reverse()
        following = list((await self.session.execute(next_statement)).scalars().all())
        return previous, following

    async def list_recent(self, *, limit: int, offset: int) -> list[MemoryModel]:
        statement = (
            select(MemoryModel)
            .where(MemoryModel.deleted_at.is_(None))
            .order_by(MemoryModel.memory_time.desc(), MemoryModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_in_range(
        self,
        start: datetime,
        end: datetime,
        *,
        include_deprecated: bool,
    ) -> list[MemoryModel]:
        statement = select(MemoryModel).where(
            MemoryModel.deleted_at.is_(None),
            MemoryModel.memory_time >= start,
            MemoryModel.memory_time < end,
        )
        if not include_deprecated:
            statement = statement.where(MemoryModel.status == MEMORY_ACTIVE)
        statement = statement.order_by(MemoryModel.memory_time, MemoryModel.id)
        return list((await self.session.execute(statement)).scalars().all())

    async def list_unsummarized(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MemoryModel]:
        covered = (
            select(MemorySummaryModel.id)
            .where(MemoryModel.id == any_(MemorySummaryModel.source_memory_ids))
            .exists()
        )
        statement = (
            select(MemoryModel)
            .where(
                MemoryModel.deleted_at.is_(None),
                MemoryModel.status == MEMORY_ACTIVE,
                MemoryModel.memory_time >= start,
                MemoryModel.memory_time < end,
                ~covered,
            )
            .order_by(MemoryModel.memory_time, MemoryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_all_ids(self) -> list[int]:
        statement = select(MemoryModel.id).where(MemoryModel.deleted_at.is_(None))
        return [int(row[0]) for row in (await self.session.execute(statement)).all()]

    async def count_active(self) -> int:
        statement = select(func.count(MemoryModel.id)).where(
            MemoryModel.deleted_at.is_(None),
            MemoryModel.status == MEMORY_ACTIVE,
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def count_all(self) -> int:
        statement = select(func.count(MemoryModel.id)).where(MemoryModel.deleted_at.is_(None))
        return int((await self.session.execute(statement)).scalar_one())
