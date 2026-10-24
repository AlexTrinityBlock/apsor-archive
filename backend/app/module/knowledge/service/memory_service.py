"""Memory timeline orchestration, supersession, and trace reads."""

from collections import deque
from datetime import UTC, datetime
from typing import cast

from app.module.knowledge.exception.domain_error import (
    InvalidQueryError,
    MemoryAlreadyDeprecatedError,
    MemoryNotFoundError,
)
from app.module.knowledge.model.chunk_model import SOURCE_MEMORY
from app.module.knowledge.model.memory_model import (
    MEMORY_ACTIVE,
    MEMORY_DEPRECATED,
    MEMORY_SOURCE_MANUAL,
    MemoryModel,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.protocol.summary_service_protocol import SummaryServiceProtocol
from app.module.knowledge.schema.memory_schema import (
    MemoryReadSchema,
    MemorySaveSchema,
    MemorySchema,
    MemorySource,
    MemoryStatus,
    SummarySchema,
)
from app.module.knowledge.service.indexer_service import IndexerService
from app.shared.time import utcnow


class MemoryService:
    """Coordinate the linear memory timeline and its search index."""

    def __init__(
        self,
        *,
        memory_repository: MemoryRepositoryProtocol,
        chunk_repository: ChunkRepositoryProtocol,
        indexer: IndexerService,
        cache: CacheProtocol,
        summary_service: SummaryServiceProtocol,
    ) -> None:
        self.memory_repository = memory_repository
        self.chunk_repository = chunk_repository
        self.indexer = indexer
        self.cache = cache
        self.summary_service = summary_service

    @staticmethod
    def _to_schema(memory: MemoryModel) -> MemorySchema:
        return MemorySchema(
            memory_id=memory.id,
            content=memory.content,
            status=cast(MemoryStatus, memory.status),
            update_time=memory.memory_time,
            supersedes_ids=list(memory.supersedes_ids),
            superseded_by_id=memory.superseded_by_id,
            source=cast(MemorySource, memory.source),
            created_at=memory.created_at,
            deleted_at=memory.deleted_at,
        )

    async def save_memory(
        self,
        *,
        content: str,
        supersedes: list[int],
        occurred_at: datetime | None,
        source: str,
        auto_summary: bool = True,
    ) -> MemorySaveSchema:
        """Create a memory, optionally deprecating the memories it replaces."""
        cleaned = content.strip()
        if not cleaned:
            raise InvalidQueryError("Memory content must not be empty.")
        unique_ids = list(dict.fromkeys(supersedes))
        if len(unique_ids) != len(supersedes):
            raise InvalidQueryError("supersedes contains duplicate ids.")

        targets: list[MemoryModel] = []
        if unique_ids:
            found = await self.memory_repository.list_by_ids(unique_ids)
            by_id = {memory.id: memory for memory in found}
            for memory_id in unique_ids:
                memory = by_id.get(memory_id)
                if memory is None or memory.deleted_at is not None:
                    raise MemoryNotFoundError(memory_id)
                if memory.status == MEMORY_DEPRECATED:
                    raise MemoryAlreadyDeprecatedError(memory_id)
                targets.append(memory)

        memory_time = occurred_at or utcnow()
        if memory_time.tzinfo is None:
            memory_time = memory_time.replace(tzinfo=UTC)

        memory = await self.memory_repository.add(
            MemoryModel(
                content=cleaned,
                status=MEMORY_ACTIVE,
                supersedes_ids=unique_ids,
                memory_time=memory_time,
                source=source or MEMORY_SOURCE_MANUAL,
            )
        )
        for target in targets:
            await self.memory_repository.deprecate(target, memory.id)
            await self.chunk_repository.mark_source_not_current(SOURCE_MEMORY, target.id)

        await self.indexer.index_single(
            source_kind=SOURCE_MEMORY,
            source_id=memory.id,
            content=memory.content,
        )
        await self.cache.bump_version()

        summary: SummarySchema | None = None
        if auto_summary:
            summary = await self.summary_service.maybe_auto_summary()

        return MemorySaveSchema(
            memory=self._to_schema(memory),
            deprecated=[self._to_schema(target) for target in targets],
            summary=summary,
        )

    async def read_memory(
        self,
        memory_id: int,
        *,
        memory_range: int,
        trace_history: bool,
    ) -> MemoryReadSchema:
        if memory_range < 0 or memory_range > 10:
            raise InvalidQueryError("memory_range must be between 0 and 10.")
        target = await self.memory_repository.get_by_id(memory_id)
        if target is None or target.deleted_at is not None:
            raise MemoryNotFoundError(memory_id)

        previous, following = await self.memory_repository.list_neighbors(
            target,
            before=memory_range,
            after=memory_range,
        )
        supersedes: list[MemoryModel] = []
        superseded_by: MemoryModel | None = None
        chain: list[MemoryModel] = [target]

        if trace_history:
            supersedes = [
                memory
                for memory in await self.memory_repository.list_by_ids(target.supersedes_ids)
                if memory.deleted_at is None
            ]
            if target.superseded_by_id is not None:
                superseded_by = await self.memory_repository.get_by_id(target.superseded_by_id)
            chain = await self._trace_chain(target)

        return MemoryReadSchema(
            target=self._to_schema(target),
            neighbors_before=[self._to_schema(memory) for memory in previous],
            neighbors_after=[self._to_schema(memory) for memory in following],
            supersedes=[self._to_schema(memory) for memory in supersedes],
            superseded_by=(self._to_schema(superseded_by) if superseded_by is not None else None),
            chain=[self._to_schema(memory) for memory in chain],
        )

    async def _trace_chain(self, target: MemoryModel) -> list[MemoryModel]:
        related: dict[int, MemoryModel] = {target.id: target}
        queue: deque[MemoryModel] = deque([target])
        while queue and len(related) < 20:
            current = queue.popleft()
            neighbor_ids = list(current.supersedes_ids)
            if current.superseded_by_id is not None:
                neighbor_ids.append(current.superseded_by_id)
            for neighbor_id in neighbor_ids:
                if neighbor_id in related:
                    continue
                neighbor = await self.memory_repository.get_by_id(neighbor_id)
                if neighbor is not None and neighbor.deleted_at is None:
                    related[neighbor.id] = neighbor
                    queue.append(neighbor)
        return sorted(
            related.values(),
            key=lambda memory: (memory.memory_time, memory.id),
        )

    async def list_memories(self, *, limit: int, offset: int) -> list[MemorySchema]:
        memories = await self.memory_repository.list_recent(limit=limit, offset=offset)
        return [self._to_schema(memory) for memory in memories]

    async def count_active(self) -> int:
        return await self.memory_repository.count_active()

    async def count_all(self) -> int:
        return await self.memory_repository.count_all()

    async def list_by_ids(self, memory_ids: list[int]) -> list[MemorySchema]:
        memories = await self.memory_repository.list_by_ids(memory_ids)
        return [self._to_schema(memory) for memory in memories]
