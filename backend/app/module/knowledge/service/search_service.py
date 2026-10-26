"""Hybrid retrieval: BM25 + vector recall fused with reciprocal rank fusion."""

import logging
import time
from collections import defaultdict
from typing import cast

from pydantic import ValidationError

from app.module.knowledge.exception.domain_error import EmbeddingProviderError, InvalidQueryError
from app.module.knowledge.model.chunk_model import (
    SOURCE_FILE,
    SOURCE_MEMORY,
    SOURCE_SUMMARY,
    ChunkModel,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import (
    ChunkRepositoryProtocol,
    VectorCandidate,
)
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_repository_protocol import FileRepositoryProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.protocol.summary_repository_protocol import SummaryRepositoryProtocol
from app.module.knowledge.schema.search_schema import (
    FileSearchResultSchema,
    MatchSource,
    MemorySearchResultSchema,
    SearchResponseSchema,
    SearchStatsSchema,
    SummarySearchResultSchema,
)
from app.module.knowledge.service.cache_keys import user_cache_key, user_version_scope
from app.shared.text.ngram import (
    fallback_unigrams,
    unique_query_terms,
)

logger = logging.getLogger(__name__)

RRF_K = 60.0
SOURCE_ORDER = (SOURCE_FILE, SOURCE_MEMORY, SOURCE_SUMMARY)
Candidate = tuple[int, str, float]


class SearchService:
    """Retrieve one owner's chunks from both paths, deduplicate, and hydrate sources."""

    def __init__(
        self,
        *,
        user_id: int,
        chunk_repository: ChunkRepositoryProtocol,
        file_repository: FileRepositoryProtocol,
        memory_repository: MemoryRepositoryProtocol,
        summary_repository: SummaryRepositoryProtocol,
        embedder: EmbedderProtocol,
        cache: CacheProtocol,
        cache_ttl_seconds: int,
        candidate_limit: int,
        vector_scan_limit: int,
    ) -> None:
        self.user_id = user_id
        self.chunk_repository = chunk_repository
        self.file_repository = file_repository
        self.memory_repository = memory_repository
        self.summary_repository = summary_repository
        self.embedder = embedder
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.candidate_limit = candidate_limit
        self.vector_scan_limit = vector_scan_limit

    async def _vector_hits(
        self,
        query: str,
        *,
        include_history: bool,
    ) -> list[VectorCandidate]:
        if self.embedder.dimension <= 0:
            return []
        try:
            vectors = await self.embedder.embed([query])
        except EmbeddingProviderError as exc:
            logger.warning("Vector recall skipped: %s", exc)
            return []
        if not vectors or not vectors[0]:
            return []
        return await self.chunk_repository.vector_candidates(
            vectors[0],
            limit=self.candidate_limit,
            scan_limit=self.vector_scan_limit,
            include_history=include_history,
        )

    @staticmethod
    def _select_per_kind(candidates: list[Candidate], result_number: int) -> list[Candidate]:
        """Take the best ``result_number`` chunks from each source kind."""
        grouped: dict[str, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate[1]].append(candidate)
        selected: list[Candidate] = []
        for source_kind in SOURCE_ORDER:
            ranked = sorted(grouped[source_kind], key=lambda item: item[2], reverse=True)
            selected.extend(ranked[:result_number])
        return selected

    async def search(
        self,
        query: str,
        *,
        result_number: int,
        include_history: bool,
    ) -> SearchResponseSchema:
        cleaned = " ".join(query.split())
        if not cleaned or len(cleaned) > 200:
            raise InvalidQueryError("query must contain between 1 and 200 characters.")
        terms = unique_query_terms(cleaned)
        if not terms:
            raise InvalidQueryError("query contains no searchable terms.")

        version = await self.cache.get_version(user_version_scope(self.user_id))
        key = user_cache_key(
            self.user_id,
            version,
            "search",
            cleaned,
            str(result_number),
            str(include_history),
        )
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            try:
                return SearchResponseSchema.model_validate(cached)
            except ValidationError:
                # 部署後舊 cache 可能缺少新欄位（例如 summary 的 memory_count）。
                # 這種 payload 視為 cache miss，不要讓使用者在 TTL 到期前看到 500。
                logger.info("Discarding an incompatible cached search response.")

        started = time.perf_counter()
        raw_text = await self.chunk_repository.text_candidates(
            terms,
            candidate_limit=self.candidate_limit,
            include_history=include_history,
        )
        used_terms = terms
        if not raw_text:
            unigrams = fallback_unigrams(terms)
            if unigrams and unigrams != terms:
                used_terms = unigrams
                raw_text = await self.chunk_repository.text_candidates(
                    unigrams,
                    candidate_limit=self.candidate_limit,
                    include_history=include_history,
                )
        text_selected = self._select_per_kind(
            [
                (candidate.chunk_id, candidate.source_kind, candidate.score)
                for candidate in raw_text
            ],
            result_number,
        )

        raw_vector = await self._vector_hits(cleaned, include_history=include_history)
        vector_selected = self._select_per_kind(
            [
                (candidate.chunk_id, candidate.source_kind, candidate.score)
                for candidate in raw_vector
            ],
            result_number,
        )

        text_ranking = {
            chunk_id: rank for rank, (chunk_id, _kind, _score) in enumerate(text_selected, start=1)
        }
        vector_ranking = {
            chunk_id: rank
            for rank, (chunk_id, _kind, _score) in enumerate(vector_selected, start=1)
        }
        union_ids = list(dict.fromkeys([*text_ranking, *vector_ranking]))
        chunks = await self.chunk_repository.get_by_ids(union_ids)
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        chunks_scanned = await self.chunk_repository.count_current()

        scored: dict[int, tuple[float, set[str]]] = {}
        for chunk_id in union_ids:
            score = 0.0
            matched: set[str] = set()
            if chunk_id in text_ranking:
                score += 1.0 / (RRF_K + text_ranking[chunk_id])
                matched.add("text")
            if chunk_id in vector_ranking:
                score += 1.0 / (RRF_K + vector_ranking[chunk_id])
                matched.add("vector")
            scored[chunk_id] = (score, matched)

        grouped: dict[str, list[tuple[ChunkModel, float, set[str]]]] = defaultdict(list)
        for chunk_id, (score, matched) in scored.items():
            chunk = chunks_by_id.get(chunk_id)
            if chunk is not None:
                grouped[chunk.source_kind].append((chunk, score, matched))

        file_chunks = sorted(grouped[SOURCE_FILE], key=lambda item: item[1], reverse=True)[
            :result_number
        ]
        memory_chunks = sorted(grouped[SOURCE_MEMORY], key=lambda item: item[1], reverse=True)[
            :result_number
        ]
        summary_chunks = sorted(grouped[SOURCE_SUMMARY], key=lambda item: item[1], reverse=True)[
            :result_number
        ]

        files = {
            file.id: file
            for file in await self.file_repository.list_by_ids(
                [chunk.source_id for chunk, _score, _matched in file_chunks]
            )
        }
        memories = {
            memory.id: memory
            for memory in await self.memory_repository.list_by_ids(
                [chunk.source_id for chunk, _score, _matched in memory_chunks]
            )
        }
        summaries = {
            summary.id: summary
            for summary in await self.summary_repository.list_by_ids(
                [chunk.source_id for chunk, _score, _matched in summary_chunks]
            )
        }

        file_results: list[FileSearchResultSchema] = []
        for chunk, score, matched in file_chunks:
            file = files.get(chunk.source_id)
            if file is None:
                continue
            file_results.append(
                FileSearchResultSchema(
                    file_id=file.id,
                    raw_file_path=file.raw_file_path,
                    file_name=file.file_name,
                    update_time=file.updated_at,
                    chunk=chunk.chunk_index,
                    chunk_id=chunk.id,
                    content=chunk.content,
                    is_current=file.is_current,
                    score=round(score, 6),
                    matched_by=self._matched(matched),
                )
            )

        memory_results: list[MemorySearchResultSchema] = []
        for chunk, score, matched in memory_chunks:
            memory = memories.get(chunk.source_id)
            if memory is None:
                continue
            memory_results.append(
                MemorySearchResultSchema(
                    memory_id=memory.id,
                    title=memory.title,
                    update_time=memory.memory_time,
                    content=memory.content,
                    status=memory.status,
                    score=round(score, 6),
                    matched_by=self._matched(matched),
                )
            )

        summary_results: list[SummarySearchResultSchema] = []
        for chunk, score, matched in summary_chunks:
            summary = summaries.get(chunk.source_id)
            if summary is None:
                continue
            summary_results.append(
                SummarySearchResultSchema(
                    memory_summary_id=summary.id,
                    update_time=summary.period_end,
                    content=summary.content,
                    period_start=summary.period_start,
                    period_end=summary.period_end,
                    themes=list(summary.themes),
                    memory_count=summary.memory_count,
                    source_memory_ids=list(summary.source_memory_ids),
                    score=round(score, 6),
                    matched_by=self._matched(matched),
                )
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response = SearchResponseSchema(
            query=cleaned,
            result_number=result_number,
            include_history=include_history,
            elapsed_ms=elapsed_ms,
            stats=SearchStatsSchema(
                text_candidates=len(text_selected),
                vector_candidates=len(vector_selected),
                merged=len(union_ids),
                deduplicated=len(text_selected) + len(vector_selected) - len(union_ids),
                chunks_scanned=chunks_scanned,
                terms=used_terms,
            ),
            file_results=file_results,
            memory_results=memory_results,
            summary_results=summary_results,
        )
        await self.cache.set_json(
            key,
            cast(dict[str, object], response.model_dump(mode="json")),
            self.cache_ttl_seconds,
        )
        return response

    @staticmethod
    def _matched(matched: set[str]) -> list[MatchSource]:
        if matched == {"text", "vector"}:
            return ["text", "vector"]
        if "text" in matched:
            return ["text"]
        if "vector" in matched:
            return ["vector"]
        return []
