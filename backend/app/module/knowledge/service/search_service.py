"""Hybrid retrieval: BM25 + vector recall fused with reciprocal rank fusion."""

import logging
import time
from collections import defaultdict
from typing import cast

from pydantic import ValidationError

from app.module.knowledge.exception.domain_error import EmbeddingProviderError, InvalidQueryError
from app.module.knowledge.model.chunk_model import (
    SOURCE_FILE,
    SOURCE_HISTORY,
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
    HistorySearchResultSchema,
    MatchSource,
    MemorySearchResultSchema,
    SearchResponseSchema,
    SearchStatsSchema,
    SummarySearchResultSchema,
)
from app.module.knowledge.service.cache_keys import user_cache_key, user_version_scope
from app.shared.retrieval import (
    HISTORY_RESULT_LIMIT,
    HISTORY_RRF_K,
    HISTORY_VECTOR_RECALL_LIMIT,
)
from app.shared.text.ngram import (
    fallback_unigrams,
    unique_query_terms,
)

logger = logging.getLogger(__name__)

RRF_K = 60.0
SOURCE_ORDER = (SOURCE_FILE, SOURCE_MEMORY, SOURCE_SUMMARY)
KNOWLEDGE_SOURCE_KINDS = (SOURCE_FILE, SOURCE_MEMORY, SOURCE_SUMMARY)
HISTORY_SOURCE_KINDS = (SOURCE_HISTORY,)
# The history lane adds a new response field. A namespace bump retires cached
# knowledge-only payloads immediately instead of waiting for their TTL.
SEARCH_CACHE_NAMESPACE = "search_v2"
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

    async def _query_embedding(self, query: str) -> list[float] | None:
        """Embed one query once for both the knowledge and history lanes."""
        if self.embedder.dimension <= 0:
            return None
        try:
            vectors = await self.embedder.embed([query])
        except EmbeddingProviderError as exc:
            logger.warning("Vector recall skipped: %s", exc)
            return None
        if not vectors or not vectors[0]:
            return None
        return vectors[0]

    async def _vector_hits(
        self,
        embedding: list[float] | None,
        *,
        include_history: bool,
    ) -> list[VectorCandidate]:
        if embedding is None:
            return []
        return await self.chunk_repository.vector_candidates(
            embedding,
            limit=self.candidate_limit,
            scan_limit=self.vector_scan_limit,
            include_history=include_history,
            source_kinds=KNOWLEDGE_SOURCE_KINDS,
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

    async def _history_hits(
        self,
        embedding: list[float] | None,
        terms: list[str],
    ) -> tuple[list[HistorySearchResultSchema], int]:
        """Recall 128 history windows, BM25-score them, then RRF-rerank to 15.

        The first stage is cosine similarity over the conversation-history
        subset. BM25 scores every recalled window against the same query using
        corpus-wide history statistics. Reciprocal rank fusion then combines
        the cosine order and the BM25 order, so a semantic-only hit keeps its
        vector rank and a lexical-only hit keeps its text rank. Deleted
        conversations are excluded because their chunks are marked non-current.
        """
        vector_candidates = (
            await self.chunk_repository.vector_candidates(
                embedding,
                limit=HISTORY_VECTOR_RECALL_LIMIT,
                scan_limit=self.vector_scan_limit,
                include_history=False,
                source_kinds=HISTORY_SOURCE_KINDS,
            )
            if embedding is not None
            else []
        )

        if vector_candidates:
            candidate_ids = [candidate.chunk_id for candidate in vector_candidates]
            vector_scores = {
                candidate.chunk_id: candidate.score for candidate in vector_candidates
            }
            text_candidates = await self.chunk_repository.bm25_for_chunk_ids(
                candidate_ids,
                terms,
                include_history=False,
                source_kinds=HISTORY_SOURCE_KINDS,
            )
            text_scores = {
                candidate.chunk_id: candidate.score for candidate in text_candidates
            }
            vector_order = [
                candidate.chunk_id
                for candidate in sorted(
                    vector_candidates,
                    key=lambda candidate: (-candidate.score, candidate.chunk_id),
                )
            ]
            text_order = sorted(
                vector_scores,
                key=lambda chunk_id: (
                    -text_scores.get(chunk_id, 0.0),
                    -vector_scores.get(chunk_id, 0.0),
                    chunk_id,
                ),
            )
            fused: dict[int, float] = {}
            for rank, chunk_id in enumerate(vector_order, start=1):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (HISTORY_RRF_K + rank)
            for rank, chunk_id in enumerate(text_order, start=1):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (HISTORY_RRF_K + rank)
            selected_ids = sorted(
                fused,
                key=lambda chunk_id: (-fused[chunk_id], chunk_id),
            )[:HISTORY_RESULT_LIMIT]
            results = await self._hydrate_history_results(
                selected_ids,
                fused=fused,
                vector_scores=vector_scores,
                text_scores=text_scores,
            )
            if results:
                return results, len(vector_candidates)

        # No vector lane (embeddings disabled or unavailable): fall back to a
        # BM25-only recall over the whole history index.
        text_candidates = await self.chunk_repository.text_candidates(
            terms,
            candidate_limit=HISTORY_VECTOR_RECALL_LIMIT,
            include_history=False,
            source_kinds=HISTORY_SOURCE_KINDS,
        )
        if not text_candidates:
            return [], 0
        rescored = await self.chunk_repository.bm25_for_chunk_ids(
            [candidate.chunk_id for candidate in text_candidates],
            terms,
            include_history=False,
            source_kinds=HISTORY_SOURCE_KINDS,
        )
        selected = sorted(
            rescored,
            key=lambda candidate: (-candidate.score, candidate.chunk_id),
        )[:HISTORY_RESULT_LIMIT]
        selected_ids = [candidate.chunk_id for candidate in selected]
        text_scores = {candidate.chunk_id: candidate.score for candidate in selected}
        fused = {
            chunk_id: 1.0 / (HISTORY_RRF_K + rank)
            for rank, chunk_id in enumerate(selected_ids, start=1)
        }
        results = await self._hydrate_history_results(
            selected_ids,
            fused=fused,
            vector_scores={},
            text_scores=text_scores,
        )
        return results, 0

    async def _hydrate_history_results(
        self,
        selected_ids: list[int],
        *,
        fused: dict[int, float],
        vector_scores: dict[int, float],
        text_scores: dict[int, float],
    ) -> list[HistorySearchResultSchema]:
        chunks = await self.chunk_repository.get_by_ids(selected_ids)
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        results: list[HistorySearchResultSchema] = []
        for chunk_id in selected_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None or chunk.source_kind != SOURCE_HISTORY:
                continue
            text_score = text_scores.get(chunk_id)
            matched: list[MatchSource] = []
            if text_score is not None and text_score > 0:
                matched.append("text")
            if chunk_id in vector_scores:
                matched.append("vector")
            if not matched:
                matched.append("text")
            results.append(
                HistorySearchResultSchema(
                    entry_id=chunk.source_id,
                    chunk_id=chunk.id,
                    chunk=chunk.chunk_index,
                    content=chunk.content,
                    score=round(fused.get(chunk_id, 0.0), 6),
                    matched_by=matched,
                    vector_score=(
                        round(vector_scores[chunk_id], 6)
                        if chunk_id in vector_scores
                        else None
                    ),
                    text_score=(
                        round(text_score, 6) if text_score is not None else None
                    ),
                )
            )
        return results

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
            SEARCH_CACHE_NAMESPACE,
            cleaned,
            str(result_number),
            str(include_history),
        )
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            try:
                return SearchResponseSchema.model_validate(cached)
            except ValidationError:
                # After a deployment an old cache entry may lack new fields (for
                # example a summary's memory_count). Such a payload counts as a
                # cache miss so the user never sees a 500 before the TTL expires.
                logger.info("Discarding an incompatible cached search response.")

        started = time.perf_counter()
        raw_text = await self.chunk_repository.text_candidates(
            terms,
            candidate_limit=self.candidate_limit,
            include_history=include_history,
            source_kinds=KNOWLEDGE_SOURCE_KINDS,
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
                    source_kinds=KNOWLEDGE_SOURCE_KINDS,
                )
        text_selected = self._select_per_kind(
            [
                (candidate.chunk_id, candidate.source_kind, candidate.score)
                for candidate in raw_text
            ],
            result_number,
        )

        embedding = await self._query_embedding(cleaned)
        raw_vector = await self._vector_hits(
            embedding,
            include_history=include_history,
        )
        vector_selected = self._select_per_kind(
            [
                (candidate.chunk_id, candidate.source_kind, candidate.score)
                for candidate in raw_vector
            ],
            result_number,
        )

        history_results, history_vector_candidates = await self._history_hits(
            embedding,
            used_terms,
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
                history_vector_candidates=history_vector_candidates,
                history_selected=len(history_results),
            ),
            file_results=file_results,
            memory_results=memory_results,
            summary_results=summary_results,
            history_results=history_results,
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
