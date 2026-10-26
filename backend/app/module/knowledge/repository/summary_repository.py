"""SQLAlchemy persistence for memory summaries.

A summary and every memory id it references belong to the same owner. The
repository enforces the owner on reads and writes; services additionally only
build ``source_memory_ids`` from owner-scoped memory queries.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.summary_model import MemorySummaryModel


class SummaryRepository:
    """Queries over one owner's periodic memory summaries."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def add(self, summary: MemorySummaryModel) -> MemorySummaryModel:
        summary.user_id = self.user_id
        self.session.add(summary)
        await self.session.flush()
        return summary

    async def get_by_id(self, summary_id: int) -> MemorySummaryModel | None:
        statement = select(MemorySummaryModel).where(
            MemorySummaryModel.id == summary_id,
            MemorySummaryModel.user_id == self.user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_recent(self, *, limit: int, offset: int) -> list[MemorySummaryModel]:
        statement = (
            select(MemorySummaryModel)
            .where(MemorySummaryModel.user_id == self.user_id)
            .order_by(MemorySummaryModel.period_end.desc(), MemorySummaryModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MemorySummaryModel]:
        statement = (
            select(MemorySummaryModel)
            .where(
                MemorySummaryModel.user_id == self.user_id,
                MemorySummaryModel.period_end >= start,
                MemorySummaryModel.period_end < end,
            )
            .order_by(MemorySummaryModel.period_end, MemorySummaryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_by_ids(self, summary_ids: Sequence[int]) -> list[MemorySummaryModel]:
        if not summary_ids:
            return []
        statement = select(MemorySummaryModel).where(
            MemorySummaryModel.user_id == self.user_id,
            MemorySummaryModel.id.in_(summary_ids),
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count(self) -> int:
        statement = select(func.count(MemorySummaryModel.id)).where(
            MemorySummaryModel.user_id == self.user_id
        )
        return int((await self.session.execute(statement)).scalar_one())
