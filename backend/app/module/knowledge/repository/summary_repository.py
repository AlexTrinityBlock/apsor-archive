"""SQLAlchemy persistence for memory summaries."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.summary_model import MemorySummaryModel


class SummaryRepository:
    """Queries over periodic memory summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, summary: MemorySummaryModel) -> MemorySummaryModel:
        self.session.add(summary)
        await self.session.flush()
        return summary

    async def get_by_id(self, summary_id: int) -> MemorySummaryModel | None:
        return await self.session.get(MemorySummaryModel, summary_id)

    async def list_recent(self, *, limit: int, offset: int) -> list[MemorySummaryModel]:
        statement = (
            select(MemorySummaryModel)
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
                MemorySummaryModel.period_end >= start,
                MemorySummaryModel.period_end < end,
            )
            .order_by(MemorySummaryModel.period_end, MemorySummaryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_by_ids(self, summary_ids: Sequence[int]) -> list[MemorySummaryModel]:
        if not summary_ids:
            return []
        statement = select(MemorySummaryModel).where(MemorySummaryModel.id.in_(summary_ids))
        return list((await self.session.execute(statement)).scalars().all())

    async def count(self) -> int:
        return int(
            (await self.session.execute(select(func.count(MemorySummaryModel.id)))).scalar_one()
        )
