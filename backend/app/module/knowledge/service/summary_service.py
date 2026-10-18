"""AI-first memory summaries with a deterministic extractive fallback."""

import json
import logging
from datetime import UTC, datetime, timedelta

from app.module.knowledge.domain.summary_domain import (
    SummaryDraft,
    SummaryMemoryInput,
    build_extractive_summary,
)
from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    InvalidTimelineRangeError,
    MemoryNotFoundError,
    SummaryNotEnoughMemoriesError,
    SummaryNotFoundError,
)
from app.module.knowledge.model.chunk_model import SOURCE_SUMMARY
from app.module.knowledge.model.memory_model import MemoryModel
from app.module.knowledge.model.summary_model import MemorySummaryModel
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.protocol.summary_repository_protocol import SummaryRepositoryProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.schema.memory_schema import SummarySchema
from app.module.knowledge.service.indexer_service import IndexerService
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = (
    "You are the archivist of a personal memory system. Summarize the supplied "
    "memories in 2 to 4 sentences, in the dominant language of those memories. "
    "Preserve specific people, objects, emotions, and causal links. Do not invent "
    "facts that are not in the memories. Return a JSON object with exactly two keys: "
    '"summary" (a string) and "themes" (an array of 3 short strings).'
)


class SummaryService:
    """Create summaries and index them into the shared chunk store."""

    def __init__(
        self,
        *,
        memory_repository: MemoryRepositoryProtocol,
        summary_repository: SummaryRepositoryProtocol,
        indexer: IndexerService,
        text_generator: TextGeneratorProtocol,
        cache: CacheProtocol,
        ai_summary_enabled: bool,
        auto_summary_threshold: int,
        min_memories: int,
    ) -> None:
        self.memory_repository = memory_repository
        self.summary_repository = summary_repository
        self.indexer = indexer
        self.text_generator = text_generator
        self.cache = cache
        self.ai_summary_enabled = ai_summary_enabled
        self.auto_summary_threshold = auto_summary_threshold
        self.min_memories = min_memories

    @staticmethod
    def _to_schema(summary: MemorySummaryModel) -> SummarySchema:
        return SummarySchema(
            memory_summary_id=summary.id,
            content=summary.content,
            period_start=summary.period_start,
            period_end=summary.period_end,
            memory_count=summary.memory_count,
            source_memory_ids=list(summary.source_memory_ids),
            themes=list(summary.themes),
            generator=summary.generator,  # type: ignore[arg-type]
            model=summary.model,
            created_at=summary.created_at,
        )

    def _memory_inputs(self, memories: list[MemoryModel]) -> list[SummaryMemoryInput]:
        return [
            SummaryMemoryInput(
                memory_id=memory.id,
                memory_time=memory.memory_time,
                content=memory.content,
            )
            for memory in memories
        ]

    async def _ai_draft(self, memories: list[MemoryModel]) -> SummaryDraft | None:
        if not self.ai_summary_enabled or not self.text_generator.configured:
            return None
        payload = [
            {
                "memory_id": memory.id,
                "time": memory.memory_time.astimezone(UTC).isoformat(),
                "content": memory.content,
            }
            for memory in memories
        ]
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            completion = await self.text_generator.complete_json(
                SUMMARY_SYSTEM_PROMPT,
                user_prompt,
            )
            body = json.loads(completion.text)
            summary_text = body["summary"]
            themes = body["themes"]
            if not isinstance(summary_text, str) or not summary_text.strip():
                return None
            if not isinstance(themes, list):
                themes = []
            cleaned_themes = [str(theme).strip() for theme in themes if str(theme).strip()][:5]
            return SummaryDraft(
                content=summary_text.strip()[:4000],
                themes=cleaned_themes,
                generator="deepseek",
                model=completion.model,
            )
        except (AiNotConfiguredError, AiProviderError, KeyError, TypeError, ValueError) as exc:
            logger.warning("AI summary failed; falling back to extractive summary: %s", exc)
            return None

    async def _create_from_memories(
        self,
        memories: list[MemoryModel],
        *,
        force: bool,
    ) -> SummarySchema:
        if len(memories) < self.min_memories and not force:
            raise SummaryNotEnoughMemoriesError(len(memories), self.min_memories)
        if not memories:
            raise SummaryNotEnoughMemoriesError(0, self.min_memories)

        ordered = sorted(memories, key=lambda memory: (memory.memory_time, memory.id))
        draft = await self._ai_draft(ordered)
        if draft is None:
            draft = build_extractive_summary(self._memory_inputs(ordered))

        summary = await self.summary_repository.add(
            MemorySummaryModel(
                content=draft.content,
                period_start=ordered[0].memory_time,
                period_end=ordered[-1].memory_time,
                memory_count=len(ordered),
                source_memory_ids=[memory.id for memory in ordered],
                themes=draft.themes,
                generator=draft.generator,
                model=draft.model,
            )
        )
        await self.indexer.index_single(
            source_kind=SOURCE_SUMMARY,
            source_id=summary.id,
            content=summary.content,
        )
        await self.cache.bump_version()
        return self._to_schema(summary)

    async def create_summary(
        self,
        *,
        period_start: datetime | None,
        period_end: datetime | None,
        memory_ids: list[int],
        force: bool,
    ) -> SummarySchema:
        """Create a summary for explicit memories or unsummarized memories in a period."""
        if memory_ids:
            unique_ids = list(dict.fromkeys(memory_ids))
            memories = await self.memory_repository.list_by_ids(unique_ids)
            found = {memory.id for memory in memories if memory.deleted_at is None}
            missing = [memory_id for memory_id in unique_ids if memory_id not in found]
            if missing:
                raise MemoryNotFoundError(missing[0])
            return await self._create_from_memories(memories, force=force)

        now = utcnow()
        start = period_start or (now - timedelta(days=30))
        end = period_end or (now + timedelta(days=1))
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end <= start:
            raise InvalidTimelineRangeError("period_end must be after period_start.")
        memories = await self.memory_repository.list_unsummarized(start, end)
        return await self._create_from_memories(memories, force=force)

    async def maybe_auto_summary(self) -> SummarySchema | None:
        """Create a summary once enough unsummarized memories have accumulated."""
        if self.auto_summary_threshold <= 0:
            return None
        now = utcnow()
        memories = await self.memory_repository.list_unsummarized(
            now - timedelta(days=365),
            now + timedelta(days=1),
        )
        if len(memories) < self.auto_summary_threshold:
            return None
        selected = memories[: self.auto_summary_threshold]
        return await self._create_from_memories(selected, force=True)

    async def get_summary(self, summary_id: int) -> SummarySchema:
        summary = await self.summary_repository.get_by_id(summary_id)
        if summary is None:
            raise SummaryNotFoundError(summary_id)
        return self._to_schema(summary)

    async def list_summaries(self, *, limit: int, offset: int) -> list[SummarySchema]:
        summaries = await self.summary_repository.list_recent(limit=limit, offset=offset)
        return [self._to_schema(summary) for summary in summaries]

    async def count_summaries(self) -> int:
        return await self.summary_repository.count()
