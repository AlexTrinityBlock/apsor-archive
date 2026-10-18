"""Persistence contract for dashboard aggregates."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class StatsSnapshot(BaseModel):
    """Aggregate counts used by the stats service."""

    model_config = ConfigDict(frozen=True)

    file_count: int
    chunk_count: int
    memory_count: int
    active_memory_count: int
    summary_count: int
    storage_bytes: int
    oldest_memory_time: datetime | None
    newest_memory_time: datetime | None


class StatsRepositoryProtocol(Protocol):
    async def snapshot(self) -> StatsSnapshot: ...
