"""Persistence contract for memory summaries."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.knowledge.model.summary_model import MemorySummaryModel


class SummaryRepositoryProtocol(Protocol):
    async def add(self, summary: MemorySummaryModel) -> MemorySummaryModel: ...

    async def get_by_id(self, summary_id: int) -> MemorySummaryModel | None: ...

    async def list_recent(self, *, limit: int, offset: int) -> list[MemorySummaryModel]: ...

    async def list_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MemorySummaryModel]: ...

    async def list_by_ids(self, summary_ids: Sequence[int]) -> list[MemorySummaryModel]: ...

    async def count(self) -> int: ...
