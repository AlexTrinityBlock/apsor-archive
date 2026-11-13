"""SQLAlchemy persistence for chunks, n-grams, BM25, and vector recall.

The repository is bound to one owner. Every chunk and n-gram predicate includes
that owner *before* limits, corpus statistics, or document-frequency counts are
computed, so a shared index never mixes two private archives.
"""

import math
from collections.abc import Sequence

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.module.knowledge.model.chunk_model import SOURCE_FILE, ChunkModel
from app.module.knowledge.model.ngram_model import ChunkNgramModel
from app.module.knowledge.protocol.chunk_repository_protocol import (
    TextCandidate,
    VectorCandidate,
)

MIN_VECTOR_SIMILARITY = 0.12


class ChunkRepository:
    """One inverted index and one vector table, scoped to one owner."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def add(self, chunk: ChunkModel) -> ChunkModel:
        chunk.user_id = self.user_id
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def add_ngrams(self, chunk_id: int, frequencies: dict[str, int]) -> None:
        if not frequencies:
            return
        rows = [
            {
                "chunk_id": chunk_id,
                "user_id": self.user_id,
                "gram": gram,
                "term_frequency": frequency,
            }
            for gram, frequency in frequencies.items()
        ]
        await self.session.execute(insert(ChunkNgramModel), rows)

    async def mark_source_not_current(self, source_kind: str, source_id: int) -> None:
        await self.session.execute(
            update(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
                ChunkModel.is_current.is_(True),
            )
            .values(is_current=False)
        )

    async def mark_sources_not_current(
        self,
        source_kind: str,
        source_ids: Sequence[int],
    ) -> None:
        if not source_ids:
            return
        await self.session.execute(
            update(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id.in_(source_ids),
                ChunkModel.is_current.is_(True),
            )
            .values(is_current=False)
        )

    async def mark_source_current(self, source_kind: str, source_id: int) -> None:
        """Publish the chunks of a staged file after its job succeeds."""
        await self.session.execute(
            update(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
            .values(is_current=True, updated_at=func.now())
        )

    async def delete_source(self, source_kind: str, source_id: int) -> None:
        """Delete staged chunks and their n-grams after a failed ingestion."""
        await self.session.execute(
            delete(ChunkNgramModel).where(
                ChunkNgramModel.user_id == self.user_id,
                ChunkNgramModel.chunk_id.in_(
                    select(ChunkModel.id).where(
                        ChunkModel.user_id == self.user_id,
                        ChunkModel.source_kind == source_kind,
                        ChunkModel.source_id == source_id,
                    )
                ),
            )
        )
        await self.session.execute(
            delete(ChunkModel).where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
        )

    async def source_ids_present(
        self,
        source_kind: str,
        source_ids: Sequence[int],
    ) -> set[int]:
        """Return which source ids already have at least one chunk row.

        Both current and non-current rows count: a deleted conversation is
        marked non-current instead of being re-indexed on the next pass.
        """
        unique_ids = list(dict.fromkeys(int(source_id) for source_id in source_ids))
        if not unique_ids:
            return set()
        statement = select(ChunkModel.source_id).where(
            ChunkModel.user_id == self.user_id,
            ChunkModel.source_kind == source_kind,
            ChunkModel.source_id.in_(unique_ids),
        )
        return {int(source_id) for source_id in (await self.session.execute(statement)).scalars()}

    async def get_source_chunks(self, source_kind: str, source_id: int) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
            .order_by(ChunkModel.chunk_index)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def clone_current_source(
        self,
        *,
        source_id: int,
        target_id: int,
    ) -> int:
        """Clone current file chunks, embeddings, and n-grams to a new file id.

        A folder copy reuses this path so identical content never calls the
        embedding provider again. Historical chunks stay on the source only.
        """
        source_chunks = await self.get_source_chunks(SOURCE_FILE, source_id)
        cloned = 0
        for chunk in source_chunks:
            if not chunk.is_current:
                continue
            duplicate = await self.add(
                ChunkModel(
                    user_id=self.user_id,
                    source_kind=SOURCE_FILE,
                    source_id=target_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    char_count=chunk.char_count,
                    token_count=chunk.token_count,
                    embedding=list(chunk.embedding) if chunk.embedding is not None else None,
                    embedding_model=chunk.embedding_model,
                    is_current=True,
                )
            )
            frequencies = await self.get_ngram_frequencies(chunk.id)
            await self.add_ngrams(duplicate.id, frequencies)
            cloned += 1
        return cloned

    async def get_ngram_frequencies(self, chunk_id: int) -> dict[str, int]:
        """Return gram -> term frequency for one chunk."""
        statement = select(ChunkNgramModel.gram, ChunkNgramModel.term_frequency).where(
            ChunkNgramModel.user_id == self.user_id,
            ChunkNgramModel.chunk_id == chunk_id,
        )
        return {
            str(gram): int(frequency)
            for gram, frequency in (await self.session.execute(statement)).all()
        }

    async def get_chunk_window(
        self,
        source_kind: str,
        source_id: int,
        start_index: int,
        end_index: int,
    ) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
                ChunkModel.chunk_index >= start_index,
                ChunkModel.chunk_index <= end_index,
            )
            .order_by(ChunkModel.chunk_index)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_by_ids(self, chunk_ids: Sequence[int]) -> list[ChunkModel]:
        if not chunk_ids:
            return []
        statement = select(ChunkModel).where(
            ChunkModel.user_id == self.user_id,
            ChunkModel.id.in_(chunk_ids),
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_current(self) -> int:
        statement = select(func.count(ChunkModel.id)).where(
            ChunkModel.user_id == self.user_id,
            ChunkModel.is_current.is_(True),
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def count_chunks(self) -> int:
        """Count every chunk owned by this account, including history."""
        return await self._count_chunks(include_history=True)

    async def embedding_model_counts(
        self,
        *,
        include_history: bool = False,
    ) -> dict[str, int]:
        statement = select(ChunkModel.embedding_model, func.count(ChunkModel.id)).where(
            ChunkModel.user_id == self.user_id,
            ChunkModel.embedding.is_not(None),
        )
        if not include_history:
            statement = statement.where(ChunkModel.is_current.is_(True))
        statement = statement.group_by(ChunkModel.embedding_model)
        return {
            str(model or "unknown"): int(count)
            for model, count in (await self.session.execute(statement)).all()
        }

    async def list_chunks_after(
        self,
        *,
        after_id: int,
        limit: int,
    ) -> list[ChunkModel]:
        """List one owner's chunks after an id, current and historical.

        Keyset pagination is used by embedding reindex so concurrent
        soft-deletes or version changes cannot shift an offset and skip rows.
        The owner predicate is part of the statement; another account's chunks
        can never enter the batch.
        """
        statement = (
            select(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.id > after_id,
            )
            .order_by(ChunkModel.id)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def update_embedding(
        self,
        chunk_id: int,
        embedding: list[float],
        model: str,
    ) -> None:
        await self.session.execute(
            update(ChunkModel)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.id == chunk_id,
            )
            .values(embedding=embedding, embedding_model=model, updated_at=func.now())
        )

    @staticmethod
    def _source_filters(
        source_kinds: Sequence[str] | None,
    ) -> list[ColumnElement[bool]]:
        """Return the optional source-kind predicate for one retrieval lane."""
        if not source_kinds:
            return []
        return [ChunkModel.source_kind.in_(tuple(source_kinds))]

    async def _count_chunks(
        self,
        include_history: bool,
        source_kinds: Sequence[str] | None = None,
    ) -> int:
        statement = select(func.count(ChunkModel.id)).where(
            ChunkModel.user_id == self.user_id,
            *self._source_filters(source_kinds),
        )
        if not include_history:
            statement = statement.where(ChunkModel.is_current.is_(True))
        return int((await self.session.execute(statement)).scalar_one())

    async def _bm25_corpus_stats(
        self,
        unique_terms: Sequence[str],
        *,
        include_history: bool,
        source_kinds: Sequence[str] | None,
    ) -> tuple[int, float, dict[str, int]]:
        """Return corpus size, average length, and term document frequencies."""
        total_chunks = await self._count_chunks(include_history, source_kinds)
        if total_chunks == 0:
            return 0, 1.0, {}

        current_filter = [] if include_history else [ChunkModel.is_current.is_(True)]
        source_filter = self._source_filters(source_kinds)
        average_length_row = await self.session.execute(
            select(func.coalesce(func.avg(ChunkModel.token_count), 0.0)).where(
                ChunkModel.user_id == self.user_id,
                *current_filter,
                *source_filter,
            )
        )
        average_length = float(average_length_row.scalar_one()) or 1.0

        frequency_rows = await self.session.execute(
            select(
                ChunkNgramModel.gram,
                func.count(func.distinct(ChunkNgramModel.chunk_id)),
            )
            .join(ChunkModel, ChunkNgramModel.chunk_id == ChunkModel.id)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkNgramModel.user_id == self.user_id,
                *current_filter,
                *source_filter,
                ChunkNgramModel.gram.in_(unique_terms),
            )
            .group_by(ChunkNgramModel.gram)
        )
        document_frequency = {str(gram): int(count) for gram, count in frequency_rows.all()}
        return total_chunks, average_length, document_frequency

    @staticmethod
    def _bm25_scores(
        *,
        total_chunks: int,
        average_length: float,
        document_frequency: dict[str, int],
        terms_by_chunk: dict[int, dict[str, int]],
        lengths: dict[int, int],
        candidate_kinds: dict[int, str],
        include_zero: bool,
    ) -> list[TextCandidate]:
        """Score known candidates with BM25, optionally retaining zero scores.

        RRF needs a rank for every vector candidate, including candidates whose
        text has no query term. The ordinary text lane keeps only positive
        scores so its result set stays meaningful.
        """
        k1 = 1.2
        b = 0.75
        scored: list[TextCandidate] = []
        for chunk_id, source_kind in candidate_kinds.items():
            frequencies = terms_by_chunk.get(chunk_id, {})
            document_length = lengths.get(chunk_id, 0)
            score = 0.0
            for gram, term_frequency in frequencies.items():
                doc_frequency = document_frequency.get(gram, 0)
                if doc_frequency == 0:
                    continue
                idf = math.log(
                    1.0 + (total_chunks - doc_frequency + 0.5) / (doc_frequency + 0.5)
                )
                denominator = term_frequency + k1 * (
                    1.0 - b + b * document_length / average_length
                )
                score += idf * (term_frequency * (k1 + 1.0) / denominator)
            if include_zero or score > 0:
                scored.append(
                    TextCandidate(
                        chunk_id=chunk_id,
                        source_kind=source_kind,
                        score=score,
                    )
                )
        scored.sort(key=lambda candidate: (-candidate.score, candidate.chunk_id))
        return scored

    async def _candidate_terms(
        self,
        candidate_ids: Sequence[int],
        unique_terms: Sequence[str],
    ) -> dict[int, dict[str, int]]:
        term_rows = await self.session.execute(
            select(
                ChunkNgramModel.chunk_id,
                ChunkNgramModel.gram,
                ChunkNgramModel.term_frequency,
            ).where(
                ChunkNgramModel.user_id == self.user_id,
                ChunkNgramModel.chunk_id.in_(candidate_ids),
                ChunkNgramModel.gram.in_(unique_terms),
            )
        )
        terms_by_chunk: dict[int, dict[str, int]] = {}
        for chunk_id, gram, frequency in term_rows.all():
            terms_by_chunk.setdefault(int(chunk_id), {})[str(gram)] = int(frequency)
        return terms_by_chunk

    async def _candidate_lengths(
        self,
        candidate_ids: Sequence[int],
    ) -> dict[int, int]:
        length_rows = await self.session.execute(
            select(ChunkModel.id, ChunkModel.token_count).where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.id.in_(candidate_ids),
            )
        )
        return {int(chunk_id): int(length) for chunk_id, length in length_rows.all()}

    async def text_candidates(
        self,
        terms: Sequence[str],
        *,
        candidate_limit: int,
        include_history: bool = False,
        source_kinds: Sequence[str] | None = None,
    ) -> list[TextCandidate]:
        unique_terms = list(dict.fromkeys(terms))
        if not unique_terms or candidate_limit <= 0:
            return []

        total_chunks, average_length, document_frequency = await self._bm25_corpus_stats(
            unique_terms,
            include_history=include_history,
            source_kinds=source_kinds,
        )
        if total_chunks == 0:
            return []

        current_filter = [] if include_history else [ChunkModel.is_current.is_(True)]
        candidate_rows = await self.session.execute(
            select(ChunkNgramModel.chunk_id, ChunkModel.source_kind)
            .join(ChunkModel, ChunkNgramModel.chunk_id == ChunkModel.id)
            .where(
                ChunkModel.user_id == self.user_id,
                ChunkNgramModel.user_id == self.user_id,
                *current_filter,
                *self._source_filters(source_kinds),
                ChunkNgramModel.gram.in_(unique_terms),
            )
            .group_by(ChunkNgramModel.chunk_id, ChunkModel.source_kind)
            .order_by(func.sum(ChunkNgramModel.term_frequency).desc())
            .limit(candidate_limit)
        )
        candidate_kinds: dict[int, str] = {}
        for chunk_id, source_kind in candidate_rows.all():
            candidate_kinds[int(chunk_id)] = str(source_kind)
        candidate_ids = list(candidate_kinds)
        if not candidate_ids:
            return []

        terms_by_chunk = await self._candidate_terms(candidate_ids, unique_terms)
        lengths = await self._candidate_lengths(candidate_ids)
        return self._bm25_scores(
            total_chunks=total_chunks,
            average_length=average_length,
            document_frequency=document_frequency,
            terms_by_chunk=terms_by_chunk,
            lengths=lengths,
            candidate_kinds=candidate_kinds,
            include_zero=False,
        )[:candidate_limit]

    async def bm25_for_chunk_ids(
        self,
        chunk_ids: Sequence[int],
        terms: Sequence[str],
        *,
        include_history: bool = False,
        source_kinds: Sequence[str] | None = None,
    ) -> list[TextCandidate]:
        """Score an explicit candidate set with corpus-wide BM25 statistics.

        The conversation-history lane uses this after vector recall: cosine
        chooses the recall set, BM25 scores every pair in that set, and RRF
        fuses the two rankings. Zero scores are retained so a semantic-only
        match still has a BM25 rank.
        """
        unique_ids = list(dict.fromkeys(int(chunk_id) for chunk_id in chunk_ids))
        unique_terms = list(dict.fromkeys(terms))
        if not unique_ids or not unique_terms:
            return []

        total_chunks, average_length, document_frequency = await self._bm25_corpus_stats(
            unique_terms,
            include_history=include_history,
            source_kinds=source_kinds,
        )
        if total_chunks == 0:
            return []

        current_filter = [] if include_history else [ChunkModel.is_current.is_(True)]
        candidate_rows = await self.session.execute(
            select(ChunkModel.id, ChunkModel.source_kind).where(
                ChunkModel.user_id == self.user_id,
                ChunkModel.id.in_(unique_ids),
                *current_filter,
                *self._source_filters(source_kinds),
            )
        )
        candidate_kinds = {
            int(chunk_id): str(source_kind)
            for chunk_id, source_kind in candidate_rows.all()
        }
        if not candidate_kinds:
            return []

        terms_by_chunk = await self._candidate_terms(list(candidate_kinds), unique_terms)
        lengths = await self._candidate_lengths(list(candidate_kinds))
        return self._bm25_scores(
            total_chunks=total_chunks,
            average_length=average_length,
            document_frequency=document_frequency,
            terms_by_chunk=terms_by_chunk,
            lengths=lengths,
            candidate_kinds=candidate_kinds,
            include_zero=True,
        )

    async def vector_candidates(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        scan_limit: int,
        include_history: bool = False,
        source_kinds: Sequence[str] | None = None,
    ) -> list[VectorCandidate]:
        if not embedding or limit <= 0:
            return []
        statement = select(
            ChunkModel.id,
            ChunkModel.source_kind,
            ChunkModel.embedding,
        ).where(
            ChunkModel.user_id == self.user_id,
            ChunkModel.embedding.is_not(None),
            *self._source_filters(source_kinds),
        )
        if not include_history:
            statement = statement.where(ChunkModel.is_current.is_(True))
        # The owner filter is part of the statement, so the scan limit applies
        # inside this account's private vector space, never the whole table.
        rows = await self.session.execute(statement.limit(scan_limit))
        query = [float(value) for value in embedding]
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            return []

        scored: list[VectorCandidate] = []
        for chunk_id, source_kind, raw in rows.all():
            if not isinstance(raw, list) or len(raw) != len(query):
                continue
            vector = [float(value) for value in raw]
            vector_norm = math.sqrt(sum(value * value for value in vector))
            if vector_norm == 0:
                continue
            dot = sum(left * right for left, right in zip(query, vector, strict=True))
            score = dot / (query_norm * vector_norm)
            if score <= MIN_VECTOR_SIMILARITY:
                continue
            scored.append(
                VectorCandidate(
                    chunk_id=int(chunk_id),
                    source_kind=str(source_kind),
                    score=score,
                )
            )
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return scored[:limit]
