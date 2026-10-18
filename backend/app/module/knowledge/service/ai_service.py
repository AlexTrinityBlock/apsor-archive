"""Retrieval-augmented answers with verifiable citations."""

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.module.knowledge.exception.domain_error import AiNotConfiguredError, AiProviderError
from app.module.knowledge.protocol.search_service_protocol import SearchServiceProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.schema.ai_schema import (
    AiStatusSchema,
    AskResponseSchema,
    CitationSchema,
)
from app.module.knowledge.schema.search_schema import (
    FileSearchResultSchema,
    MemorySearchResultSchema,
    SearchResponseSchema,
    SummarySearchResultSchema,
)

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"\[(memory|file|summary):([0-9]+)(?:#([0-9]+))?\]")
MAX_CONTEXT_CHARS = 12_000
MAX_SOURCES = 12
RRF_K = 60.0

ANSWER_SYSTEM_PROMPT = (
    "You are DendroMatrix, the user's second brain. Answer only from the SOURCES "
    "provided. Cite every factual claim with the exact source label in square "
    "brackets, for example [memory:1015] or [file:12#3]. Never invent a label or a "
    "fact. If the sources do not contain the answer, say so plainly. Answer in the "
    "same language as the question."
)

EXPANSION_SYSTEM_PROMPT = (
    "You expand a question into short retrieval queries for a personal knowledge "
    'archive. Return JSON with exactly one key, "queries", containing 2 to 4 short '
    "queries in the same language as the question. Keep named entities, dates, and "
    "key nouns. Do not answer the question."
)


@dataclass(frozen=True)
class _Source:
    kind: str
    label: str
    excerpt: str
    time: datetime
    file_id: int | None = None
    chunk: int | None = None
    raw_file_path: str | None = None
    memory_id: int | None = None
    memory_summary_id: int | None = None


class AiService:
    """Run retrieval, build bounded context, and ask DeepSeek for an answer."""

    def __init__(
        self,
        *,
        search_service: SearchServiceProtocol,
        text_generator: TextGeneratorProtocol,
        embedding_provider: str,
        embedding_model: str,
        vector_enabled: bool,
    ) -> None:
        self.search_service = search_service
        self.text_generator = text_generator
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.vector_enabled = vector_enabled

    @staticmethod
    def _sources(
        file_results: list[FileSearchResultSchema],
        memory_results: list[MemorySearchResultSchema],
        summary_results: list[SummarySearchResultSchema],
    ) -> list[_Source]:
        sources: list[_Source] = []
        for file_result in file_results:
            sources.append(
                _Source(
                    kind="file",
                    label=f"file:{file_result.file_id}#{file_result.chunk}",
                    excerpt=file_result.content,
                    time=file_result.update_time,
                    file_id=file_result.file_id,
                    chunk=file_result.chunk,
                    raw_file_path=file_result.raw_file_path,
                )
            )
        for memory_result in memory_results:
            sources.append(
                _Source(
                    kind="memory",
                    label=f"memory:{memory_result.memory_id}",
                    excerpt=memory_result.content,
                    time=memory_result.update_time,
                    memory_id=memory_result.memory_id,
                )
            )
        for summary_result in summary_results:
            sources.append(
                _Source(
                    kind="summary",
                    label=f"summary:{summary_result.memory_summary_id}",
                    excerpt=summary_result.content,
                    time=summary_result.update_time,
                    memory_summary_id=summary_result.memory_summary_id,
                )
            )
        return sources[:MAX_SOURCES]

    @staticmethod
    def _context(sources: list[_Source]) -> str:
        blocks: list[str] = []
        used = 0
        for source in sources:
            header = (
                f"[{source.label} | {source.time.isoformat()}"
                + (f" | {source.raw_file_path}" if source.raw_file_path else "")
                + "]"
            )
            block = f"{header}\n{source.excerpt.strip()}"
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            blocks.append(block)
            used += len(block)
        return "\n\n".join(blocks)

    async def _expanded_queries(self, question: str) -> list[str]:
        """Ask the model for a few retrieval queries; never block the answer."""
        try:
            completion = await self.text_generator.complete_json(
                EXPANSION_SYSTEM_PROMPT,
                question,
            )
            body = json.loads(completion.text)
            raw_queries = body.get("queries")
            if not isinstance(raw_queries, list):
                return [question]
            unique: list[str] = []
            seen = {question.strip().lower()}
            for raw_query in raw_queries:
                query = str(raw_query).strip()
                if not query or query.lower() in seen:
                    continue
                seen.add(query.lower())
                unique.append(query)
            return [question, *unique[:3]]
        except (AiProviderError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Query expansion failed; using the original question: %s", exc)
            return [question]

    @staticmethod
    def _merge_searches(
        searches: list[SearchResponseSchema],
        result_number: int,
    ) -> tuple[
        list[FileSearchResultSchema],
        list[MemorySearchResultSchema],
        list[SummarySearchResultSchema],
    ]:
        """Fuse multiple query runs by reciprocal rank, then deduplicate."""
        file_scores: defaultdict[tuple[int, int], float] = defaultdict(float)
        memory_scores: defaultdict[int, float] = defaultdict(float)
        summary_scores: defaultdict[int, float] = defaultdict(float)
        files: dict[tuple[int, int], FileSearchResultSchema] = {}
        memories: dict[int, MemorySearchResultSchema] = {}
        summaries: dict[int, SummarySearchResultSchema] = {}

        for search in searches:
            for rank, file_item in enumerate(search.file_results, start=1):
                key = (file_item.file_id, file_item.chunk)
                files[key] = file_item
                file_scores[key] += 1.0 / (RRF_K + rank)
            for rank, memory_item in enumerate(search.memory_results, start=1):
                memories[memory_item.memory_id] = memory_item
                memory_scores[memory_item.memory_id] += 1.0 / (RRF_K + rank)
            for rank, summary_item in enumerate(search.summary_results, start=1):
                summaries[summary_item.memory_summary_id] = summary_item
                summary_scores[summary_item.memory_summary_id] += 1.0 / (RRF_K + rank)

        top_files = sorted(file_scores, key=lambda key: file_scores[key], reverse=True)[
            :result_number
        ]
        top_memories = sorted(
            memory_scores,
            key=lambda key: memory_scores[key],
            reverse=True,
        )[:result_number]
        top_summaries = sorted(
            summary_scores,
            key=lambda key: summary_scores[key],
            reverse=True,
        )[:result_number]
        return (
            [files[key] for key in top_files],
            [memories[key] for key in top_memories],
            [summaries[key] for key in top_summaries],
        )

    async def ask(self, *, question: str, result_number: int) -> AskResponseSchema:
        if not self.text_generator.configured:
            raise AiNotConfiguredError()

        started = time.perf_counter()
        search_queries = await self._expanded_queries(question)
        searches = [
            await self.search_service.search(
                query,
                result_number=result_number,
                include_history=False,
            )
            for query in search_queries
        ]
        file_results, memory_results, summary_results = self._merge_searches(
            searches,
            result_number,
        )
        sources = self._sources(file_results, memory_results, summary_results)
        retrieved = {
            "files": len(file_results),
            "memories": len(memory_results),
            "summaries": len(summary_results),
        }
        if not sources:
            return AskResponseSchema(
                answer="No matching knowledge was found in the library.",
                citations=[],
                model="none",
                usage={},
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                retrieved=retrieved,
                search_queries=search_queries,
            )

        user_prompt = f"QUESTION:\n{question}\n\nSOURCES:\n{self._context(sources)}"
        completion = await self.text_generator.complete_text(
            ANSWER_SYSTEM_PROMPT,
            user_prompt,
        )
        cited_labels = {
            f"{kind}:{source_id}" + (f"#{chunk}" if chunk else "")
            for kind, source_id, chunk in CITATION_PATTERN.findall(completion.text)
        }
        citations = [
            CitationSchema(
                kind=source.kind,  # type: ignore[arg-type]
                label=source.label,
                excerpt=source.excerpt[:600],
                time=source.time,
                cited=source.label in cited_labels,
                file_id=source.file_id,
                chunk=source.chunk,
                raw_file_path=source.raw_file_path,
                memory_id=source.memory_id,
                memory_summary_id=source.memory_summary_id,
            )
            for source in sources
        ]
        citations.sort(key=lambda citation: (not citation.cited, citation.kind, citation.label))
        return AskResponseSchema(
            answer=completion.text,
            citations=citations,
            model=completion.model,
            usage=completion.usage,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            retrieved=retrieved,
            search_queries=search_queries,
        )

    def status(self) -> AiStatusSchema:
        return AiStatusSchema(
            configured=self.text_generator.configured,
            model=self.text_generator.model_name,
            provider="deepseek" if self.text_generator.configured else "none",
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            vector_enabled=self.vector_enabled,
        )
