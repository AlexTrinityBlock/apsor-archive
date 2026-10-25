"""Persistence contract for memories."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.knowledge.model.memory_model import MemoryModel


class MemoryRepositoryProtocol(Protocol):
    async def add(self, memory: MemoryModel) -> MemoryModel: ...

    async def get_by_id(self, memory_id: int) -> MemoryModel | None: ...

    async def save(self, memory: MemoryModel) -> MemoryModel: ...

    async def list_by_ids(self, memory_ids: Sequence[int]) -> list[MemoryModel]: ...

    async def deprecate(
        self,
        memory: MemoryModel,
        successor_id: int | None = None,
        *,
        reason: str | None = None,
    ) -> None: ...

    async def list_neighbors(
        self,
        target: MemoryModel,
        *,
        before: int,
        after: int,
    ) -> tuple[list[MemoryModel], list[MemoryModel]]: ...

    async def list_recent(self, *, limit: int, offset: int) -> list[MemoryModel]: ...

    async def list_in_range(
        self,
        start: datetime,
        end: datetime,
        *,
        include_deprecated: bool,
    ) -> list[MemoryModel]: ...

    async def list_unsummarized(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MemoryModel]: ...

    async def list_all_ids(self) -> list[int]: ...

    async def count_active(self) -> int: ...

    async def count_all(self) -> int: ...
