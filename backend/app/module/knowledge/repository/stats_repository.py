"""Aggregate queries for the dashboard and health screens."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.model.file_model import FileModel
from app.module.knowledge.model.memory_model import MEMORY_ACTIVE, MemoryModel
from app.module.knowledge.model.summary_model import MemorySummaryModel
from app.module.knowledge.protocol.stats_repository_protocol import StatsSnapshot


class StatsRepository:
    """Read-only aggregate queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(self) -> StatsSnapshot:
        file_count = int(
            (
                await self.session.execute(
                    select(func.count(FileModel.id)).where(
                        FileModel.is_current.is_(True),
                        FileModel.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
        )
        chunk_count = int(
            (
                await self.session.execute(
                    select(func.count(ChunkModel.id)).where(ChunkModel.is_current.is_(True))
                )
            ).scalar_one()
        )
        memory_count = int(
            (
                await self.session.execute(
                    select(func.count(MemoryModel.id)).where(MemoryModel.deleted_at.is_(None))
                )
            ).scalar_one()
        )
        active_memory_count = int(
            (
                await self.session.execute(
                    select(func.count(MemoryModel.id)).where(
                        MemoryModel.deleted_at.is_(None),
                        MemoryModel.status == MEMORY_ACTIVE,
                    )
                )
            ).scalar_one()
        )
        summary_count = int(
            (await self.session.execute(select(func.count(MemorySummaryModel.id)))).scalar_one()
        )
        storage_bytes = int(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(FileModel.size_bytes), 0)).where(
                        FileModel.is_current.is_(True),
                        FileModel.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
        )
        time_row = (
            await self.session.execute(
                select(
                    func.min(MemoryModel.memory_time),
                    func.max(MemoryModel.memory_time),
                ).where(MemoryModel.deleted_at.is_(None))
            )
        ).one()
        return StatsSnapshot(
            file_count=file_count,
            chunk_count=chunk_count,
            memory_count=memory_count,
            active_memory_count=active_memory_count,
            summary_count=summary_count,
            storage_bytes=storage_bytes,
            oldest_memory_time=time_row[0],
            newest_memory_time=time_row[1],
        )
