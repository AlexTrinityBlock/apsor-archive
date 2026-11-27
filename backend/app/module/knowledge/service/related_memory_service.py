"""Rank the memories related to one memory or one file.

Related memories reuse what ingestion already stored: each source chunk's
embedding and n-gram frequencies. No provider is called and no embedding quota
is spent. Two lanes run inside the owner's private index:

* ``similar`` — cosine similarity against the source's stored embedding (a
  file uses the normalized mean of its first chunk embeddings);
* ``keyword`` — BM25 over the source's most frequent n-gram terms.

Lanes are fused with reciprocal rank fusion, then summaries that contain the
source memory add a ``summary`` bonus. Time proximity only breaks ties and tags
``nearby``; the reader already lists timeline neighbours. The source and its
supersession chain are excluded because Lineage and Chain already show them.
"""

import math
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from app.module.knowledge.exception.domain_error import (
    FileRecordNotFoundError,
    InvalidQueryError,
    MemoryNotFoundError,
)
from app.module.knowledge.model.chunk_model import SOURCE_FILE, SOURCE_MEMORY, ChunkModel
from app.module.knowledge.model.memory_model import MEMORY_DEPRECATED, MemoryModel
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.file_repository_protocol import FileRepositoryProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.protocol.summary_repository_protocol import (
    SummaryRepositoryProtocol,
)
from app.module.knowledge.schema.memory_schema import (
    MemorySchema,
    MemorySource,
    MemoryStatus,
    RelatedMemoriesSchema,
    RelatedMemorySchema,
    RelatedReason,
)
from app.module.knowledge.service.cache_keys import user_cache_key, user_version_scope

RRF_K = 60.0
MAX_LIMIT = 20
LANE_DEPTH = 40
KEYWORD_TERMS = 12
FILE_VECTOR_CHUNKS = 8
CHAIN_LIMIT = 20
NEARBY_DAYS = 7
TIME_TIE_BREAK = 0.002
RELATED_CACHE_NAMESPACE = "related_v1"
REASON_ORDER: tuple[RelatedReason, ...] = ("similar", "keyword", "summary", "nearby")


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float] | None:
    """Average same-length vectors and normalize the result."""
    usable = [list(vector) for vector in vectors if vector]
    if not usable:
        return None
    size = len(usable[0])
    usable = [vector for vector in usable if len(vector) == size]
    total = [sum(vector[index] for vector in usable) for index in range(size)]
    norm = math.sqrt(sum(value * value for value in total))
    if norm == 0:
        return None
    return [value / norm for value in total]


def _top_terms(frequencies: Sequence[dict[str, int]], limit: int) -> list[str]:
    """Pick the most frequent n-gram terms across the source chunks."""
    merged: dict[str, int] = {}
    for item in frequencies:
        for term, count in item.items():
            merged[term] = merged.get(term, 0) + count
    ranked = sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))
    return [term for term, _count in ranked[:limit]]


def _days_apart(left: datetime, right: datetime) -> float:
    return abs((left - right).total_seconds()) / 86400.0


class RelatedMemoryService:
    """Owner-scoped related-memory ranking over stored embeddings and n-grams."""

    def __init__(
        self,
        *,
        user_id: int,
        memory_repository: MemoryRepositoryProtocol,
        file_repository: FileRepositoryProtocol,
        chunk_repository: ChunkRepositoryProtocol,
        summary_repository: SummaryRepositoryProtocol,
        cache: CacheProtocol,
        cache_ttl_seconds: int,
        vector_scan_limit: int,
    ) -> None:
        self.user_id = user_id
        self.memory_repository = memory_repository
        self.file_repository = file_repository
        self.chunk_repository = chunk_repository
        self.summary_repository = summary_repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.vector_scan_limit = vector_scan_limit

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

    @staticmethod
    def _check_limit(limit: int) -> None:
        if limit < 1 or limit > MAX_LIMIT:
            raise InvalidQueryError(f"limit must be between 1 and {MAX_LIMIT}.")

    async def _cached(self, *parts: str) -> tuple[str, RelatedMemoriesSchema | None]:
        version = await self.cache.get_version(user_version_scope(self.user_id))
        key = user_cache_key(self.user_id, version, RELATED_CACHE_NAMESPACE, *parts)
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            try:
                return key, RelatedMemoriesSchema.model_validate(cached)
            except ValueError:
                return key, None
        return key, None

    async def _store(self, key: str, value: RelatedMemoriesSchema) -> None:
        await self.cache.set_json(key, value.model_dump(mode="json"), self.cache_ttl_seconds)

    async def _chain_ids(self, target: MemoryModel) -> set[int]:
        seen: set[int] = {target.id}
        frontier: list[MemoryModel] = [target]
        while frontier and len(seen) < CHAIN_LIMIT:
            current = frontier.pop()
            neighbor_ids = list(current.supersedes_ids)
            if current.superseded_by_id is not None:
                neighbor_ids.append(current.superseded_by_id)
            for neighbor_id in neighbor_ids:
                if neighbor_id in seen:
                    continue
                seen.add(neighbor_id)
                neighbor = await self.memory_repository.get_by_id(neighbor_id)
                if neighbor is not None:
                    frontier.append(neighbor)
        return seen

    async def _lane_rankings(
        self,
        chunks: Sequence[ChunkModel],
        vector: list[float] | None,
        *,
        include_history: bool,
    ) -> tuple[dict[int, int], dict[int, int]]:
        """Return memory-id rank maps for the vector and keyword lanes.

        Deprecated memories leave the current index, so including them means
        scanning non-current memory chunks as well.
        """
        vector_rank: dict[int, int] = {}
        keyword_rank: dict[int, int] = {}
        candidate_chunk_ids: list[int] = []
        vector_ids: list[int] = []
        if vector is not None:
            hits = await self.chunk_repository.vector_candidates(
                vector,
                limit=LANE_DEPTH,
                scan_limit=self.vector_scan_limit,
                include_history=include_history,
                source_kinds=(SOURCE_MEMORY,),
            )
            vector_ids = [hit.chunk_id for hit in hits]
            candidate_chunk_ids.extend(vector_ids)

        frequencies = [
            await self.chunk_repository.get_ngram_frequencies(chunk.id)
            for chunk in chunks[:FILE_VECTOR_CHUNKS]
        ]
        terms = _top_terms(frequencies, KEYWORD_TERMS)
        keyword_ids: list[int] = []
        if terms:
            text_hits = await self.chunk_repository.text_candidates(
                terms,
                candidate_limit=LANE_DEPTH,
                include_history=include_history,
                source_kinds=(SOURCE_MEMORY,),
            )
            keyword_ids = [hit.chunk_id for hit in text_hits]
            candidate_chunk_ids.extend(keyword_ids)

        hydrated = await self.chunk_repository.get_by_ids(list(dict.fromkeys(candidate_chunk_ids)))
        memory_of = {chunk.id: chunk.source_id for chunk in hydrated}
        for ids, ranking in ((vector_ids, vector_rank), (keyword_ids, keyword_rank)):
            for chunk_id in ids:
                memory_id = memory_of.get(chunk_id)
                if memory_id is not None and memory_id not in ranking:
                    ranking[memory_id] = len(ranking) + 1
        return vector_rank, keyword_rank

    async def _rank(
        self,
        *,
        source_kind: str,
        source_id: int,
        chunks: Sequence[ChunkModel],
        vector: list[float] | None,
        anchor_time: datetime | None,
        excluded: set[int],
        summary_members: dict[int, list[int]],
        limit: int,
        include_deprecated: bool,
    ) -> RelatedMemoriesSchema:
        vector_rank, keyword_rank = await self._lane_rankings(
            chunks,
            vector,
            include_history=include_deprecated,
        )
        scores: dict[int, float] = {}
        reasons: dict[int, set[RelatedReason]] = {}
        for memory_id, rank in vector_rank.items():
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (RRF_K + rank)
            reasons.setdefault(memory_id, set()).add("similar")
        for memory_id, rank in keyword_rank.items():
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (RRF_K + rank)
            reasons.setdefault(memory_id, set()).add("keyword")
        for memory_id in summary_members:
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (RRF_K + 1)
            reasons.setdefault(memory_id, set()).add("summary")

        candidate_ids = [memory_id for memory_id in scores if memory_id not in excluded]
        memories = await self.memory_repository.list_by_ids(candidate_ids)
        ranked: list[RelatedMemorySchema] = []
        for memory in memories:
            if memory.deleted_at is not None:
                continue
            if memory.status == MEMORY_DEPRECATED and not include_deprecated:
                continue
            score = scores[memory.id]
            memory_reasons = set(reasons[memory.id])
            if anchor_time is not None:
                days = _days_apart(memory.memory_time, anchor_time)
                score += TIME_TIE_BREAK / (1.0 + days / 30.0)
                if days <= NEARBY_DAYS:
                    memory_reasons.add("nearby")
            ranked.append(
                RelatedMemorySchema(
                    memory=self._to_schema(memory),
                    score=round(score, 6),
                    reasons=[reason for reason in REASON_ORDER if reason in memory_reasons],
                    shared_summary_ids=sorted(summary_members.get(memory.id, [])),
                )
            )
        ranked.sort(key=lambda item: (-item.score, -item.memory.memory_id))
        return RelatedMemoriesSchema(
            source_kind="memory" if source_kind == SOURCE_MEMORY else "file",
            source_id=source_id,
            similarity_available=vector is not None,
            resources=ranked[:limit],
        )

    async def related_to_memory(
        self,
        memory_id: int,
        *,
        limit: int,
        include_deprecated: bool,
    ) -> RelatedMemoriesSchema:
        """Rank memories related to one memory, excluding its supersession chain."""
        self._check_limit(limit)
        target = await self.memory_repository.get_by_id(memory_id)
        if target is None or target.deleted_at is not None:
            raise MemoryNotFoundError(memory_id)
        key, cached = await self._cached(
            "memory", str(memory_id), str(limit), str(include_deprecated)
        )
        if cached is not None:
            return cached

        chunks = [
            chunk
            for chunk in await self.chunk_repository.get_source_chunks(SOURCE_MEMORY, memory_id)
            if chunk.is_current
        ]
        vector = _mean_vector(
            [embedding for chunk in chunks if (embedding := chunk.embedding_as_list())]
        )
        summary_members: dict[int, list[int]] = {}
        for summary in await self.summary_repository.list_containing_memory(memory_id):
            for member_id in summary.source_memory_ids:
                summary_members.setdefault(int(member_id), []).append(summary.id)
        result = await self._rank(
            source_kind=SOURCE_MEMORY,
            source_id=memory_id,
            chunks=chunks,
            vector=vector,
            anchor_time=target.memory_time,
            excluded=await self._chain_ids(target),
            summary_members=summary_members,
            limit=limit,
            include_deprecated=include_deprecated,
        )
        await self._store(key, result)
        return result

    async def related_to_file(self, file_id: int, *, limit: int) -> RelatedMemoriesSchema:
        """Rank memories related to one current file version."""
        self._check_limit(limit)
        file = await self.file_repository.get_by_id(file_id)
        if file is None or file.deleted_at is not None:
            raise FileRecordNotFoundError(file_id)
        empty = RelatedMemoriesSchema(
            source_kind="file",
            source_id=file_id,
            similarity_available=False,
            resources=[],
        )
        if not file.is_current:
            return empty
        key, cached = await self._cached("file", str(file_id), str(limit))
        if cached is not None:
            return cached

        chunks = sorted(
            (
                chunk
                for chunk in await self.chunk_repository.get_source_chunks(SOURCE_FILE, file_id)
                if chunk.is_current
            ),
            key=lambda chunk: chunk.chunk_index,
        )
        vector = _mean_vector(
            [
                embedding
                for chunk in chunks[:FILE_VECTOR_CHUNKS]
                if (embedding := chunk.embedding_as_list())
            ]
        )
        result = await self._rank(
            source_kind=SOURCE_FILE,
            source_id=file_id,
            chunks=chunks,
            vector=vector,
            anchor_time=None,
            excluded=set(),
            summary_members={},
            limit=limit,
            include_deprecated=False,
        )
        await self._store(key, result)
        return result
