"""Memory timeline orchestration, supersession, and trace reads."""

import json
import logging
from collections import deque
from datetime import UTC, datetime
from typing import cast

from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
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
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
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

logger = logging.getLogger(__name__)

MEMORY_TITLE_SYSTEM_PROMPT = (
    "You name entries in a personal archive. Return a JSON object with exactly "
    'one key, "title": a concise noun phrase in the dominant language of the '
    "memory, 2 to 10 words and at most 80 characters. Do not use quotation "
    "marks, a trailing period, or invented facts."
)
MEMORY_TITLE_LIMIT = 120


def _fallback_title(content: str) -> str:
    """Derive a stable title when no AI provider is configured or reachable."""
    compact = " ".join(content.split())
    if not compact:
        return "Untitled memory"
    return compact[:80].rstrip(" ,.;:!?。，；：！？") or "Untitled memory"


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
        text_generator: TextGeneratorProtocol,
    ) -> None:
        self.memory_repository = memory_repository
        self.chunk_repository = chunk_repository
        self.indexer = indexer
        self.cache = cache
        self.summary_service = summary_service
        self.text_generator = text_generator

    @staticmethod
    def _to_schema(memory: MemoryModel) -> MemorySchema:
        return MemorySchema(
            memory_id=memory.id,
            title=memory.title,
            content=memory.content,
            status=cast(MemoryStatus, memory.status),
            update_time=memory.memory_time,
            supersedes_ids=list(memory.supersedes_ids),
            superseded_by_id=memory.superseded_by_id,
            deprecated_at=memory.deprecated_at,
            deprecated_reason=memory.deprecated_reason,
            source=cast(MemorySource, memory.source),
            created_at=memory.created_at,
            deleted_at=memory.deleted_at,
        )

    async def _generate_title(self, content: str) -> str:
        """Name a memory before its single atomic insert.

        The provider call happens before the row is written, so a memory is
        never stored without a title. A missing provider or malformed response
        falls back to deterministic text instead of failing the save.
        """
        if self.text_generator.configured:
            try:
                completion = await self.text_generator.complete_json(
                    MEMORY_TITLE_SYSTEM_PROMPT,
                    content[:8000],
                )
                text = completion.text.strip()
                start = text.find("{")
                end = text.rfind("}")
                body = json.loads(text[start : end + 1] if start >= 0 and end > start else text)
                raw_title = body["title"]
                title = " ".join(str(raw_title).split()).strip(" \t\"'“”‘’")
                title = title.rstrip("。.!?！？;；,，")
                if title:
                    return title[:MEMORY_TITLE_LIMIT]
            except (AiNotConfiguredError, AiProviderError, KeyError, TypeError, ValueError):
                logger.debug("Falling back to a derived memory title.", exc_info=True)
        return _fallback_title(content)[:MEMORY_TITLE_LIMIT]

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

        title = await self._generate_title(cleaned)
        memory = await self.memory_repository.add(
            MemoryModel(
                title=title,
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

    async def update_memory(self, memory_id: int, *, content: str) -> MemorySchema:
        """Edit one memory in place and republish its search chunk.

        The old chunk stays in the ledger as history but is marked non-current.
        Editing a deprecated memory keeps it deprecated and keeps its new chunk
        out of retrieval; the row remains readable with its replacement content.
        """
        cleaned = content.strip()
        if not cleaned:
            raise InvalidQueryError("Memory content must not be empty.")
        memory = await self.memory_repository.get_by_id(memory_id)
        if memory is None or memory.deleted_at is not None:
            raise MemoryNotFoundError(memory_id)
        if memory.content == cleaned:
            return self._to_schema(memory)

        # Generate the new name before the single flush so body and title always
        # change together. The fallback tracks the new body when the provider is
        # unavailable, so a stale title never outlives an edit.
        memory.title = await self._generate_title(cleaned)
        memory.content = cleaned
        await self.memory_repository.save(memory)
        await self.chunk_repository.mark_source_not_current(SOURCE_MEMORY, memory.id)
        await self.indexer.index_single(
            source_kind=SOURCE_MEMORY,
            source_id=memory.id,
            content=memory.content,
        )
        if memory.status == MEMORY_DEPRECATED:
            await self.chunk_repository.mark_source_not_current(SOURCE_MEMORY, memory.id)
        await self.cache.bump_version()
        return self._to_schema(memory)

    async def deprecate_memory(
        self,
        memory_id: int,
        *,
        reason: str | None = None,
    ) -> MemorySchema:
        """Retire exactly one memory without creating a successor."""
        deprecated = await self.deprecate_memories([memory_id], reason=reason)
        return deprecated[0]

    async def deprecate_memories(
        self,
        memory_ids: list[int],
        *,
        reason: str | None = None,
    ) -> list[MemorySchema]:
        """Retire several memories in one transaction, without replacements.

        Every id is validated before any row changes, so a batch with one stale
        id leaves the whole set active. The search chunks become non-current and
        the archive cache is bumped once.
        """
        unique_ids = list(dict.fromkeys(memory_ids))
        if not unique_ids:
            raise InvalidQueryError("At least one memory id is required.")
        if len(unique_ids) != len(memory_ids):
            raise InvalidQueryError("deprecate contains duplicate ids.")
        cleaned_reason = reason.strip() if isinstance(reason, str) else None
        if not cleaned_reason:
            cleaned_reason = None

        found = await self.memory_repository.list_by_ids(unique_ids)
        by_id = {memory.id: memory for memory in found}
        targets: list[MemoryModel] = []
        for memory_id in unique_ids:
            memory = by_id.get(memory_id)
            if memory is None or memory.deleted_at is not None:
                raise MemoryNotFoundError(memory_id)
            if memory.status == MEMORY_DEPRECATED:
                raise MemoryAlreadyDeprecatedError(memory_id)
            targets.append(memory)

        for target in targets:
            await self.memory_repository.deprecate(target, reason=cleaned_reason)
            await self.chunk_repository.mark_source_not_current(SOURCE_MEMORY, target.id)
        await self.cache.bump_version()
        return [self._to_schema(target) for target in targets]

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
