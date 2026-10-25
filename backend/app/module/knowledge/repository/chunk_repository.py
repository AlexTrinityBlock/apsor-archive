"""SQLAlchemy persistence for chunks, n-grams, BM25, and vector recall."""

import math
from collections.abc import Sequence

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.model.ngram_model import ChunkNgramModel
from app.module.knowledge.protocol.chunk_repository_protocol import (
    TextCandidate,
    VectorCandidate,
)

MIN_VECTOR_SIMILARITY = 0.12


class ChunkRepository:
    """One inverted index and one vector table for every knowledge source."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, chunk: ChunkModel) -> ChunkModel:
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def add_ngrams(self, chunk_id: int, frequencies: dict[str, int]) -> None:
        if not frequencies:
            return
        rows = [
            {"chunk_id": chunk_id, "gram": gram, "term_frequency": frequency}
            for gram, frequency in frequencies.items()
        ]
        await self.session.execute(insert(ChunkNgramModel), rows)

    async def mark_source_not_current(self, source_kind: str, source_id: int) -> None:
        await self.session.execute(
            update(ChunkModel)
            .where(
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
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
            .values(is_current=True, updated_at=func.now())
        )

    async def delete_source(self, source_kind: str, source_id: int) -> None:
        """Delete staged chunks and their n-grams after a failed ingestion."""
        await self.session.execute(
            delete(ChunkNgramModel).where(
                ChunkNgramModel.chunk_id.in_(
                    select(ChunkModel.id).where(
                        ChunkModel.source_kind == source_kind,
                        ChunkModel.source_id == source_id,
                    )
                )
            )
        )
        await self.session.execute(
            delete(ChunkModel).where(
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
        )

    async def get_source_chunks(self, source_kind: str, source_id: int) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(
                ChunkModel.source_kind == source_kind,
                ChunkModel.source_id == source_id,
            )
            .order_by(ChunkModel.chunk_index)
        )
        return list((await self.session.execute(statement)).scalars().all())

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
        statement = select(ChunkModel).where(ChunkModel.id.in_(chunk_ids))
        return list((await self.session.execute(statement)).scalars().all())

    async def count_current(self) -> int:
        statement = select(func.count(ChunkModel.id)).where(ChunkModel.is_current.is_(True))
        return int((await self.session.execute(statement)).scalar_one())

    async def embedding_model_counts(self) -> dict[str, int]:
        statement = (
            select(ChunkModel.embedding_model, func.count(ChunkModel.id))
            .where(
                ChunkModel.is_current.is_(True),
                ChunkModel.embedding.is_not(None),
            )
            .group_by(ChunkModel.embedding_model)
        )
        return {
            str(model or "unknown"): int(count)
            for model, count in (await self.session.execute(statement)).all()
        }

    async def list_current_chunks(self, *, limit: int, offset: int) -> list[ChunkModel]:
        statement = (
            select(ChunkModel)
            .where(ChunkModel.is_current.is_(True))
            .order_by(ChunkModel.id)
            .offset(offset)
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
            .where(ChunkModel.id == chunk_id)
            .values(embedding=embedding, embedding_model=model, updated_at=func.now())
        )

    async def _count_chunks(self, include_history: bool) -> int:
        statement = select(func.count(ChunkModel.id))
        if not include_history:
            statement = statement.where(ChunkModel.is_current.is_(True))
        return int((await self.session.execute(statement)).scalar_one())

    async def text_candidates(
        self,
        terms: Sequence[str],
        *,
        candidate_limit: int,
        include_history: bool = False,
    ) -> list[TextCandidate]:
        unique_terms = list(dict.fromkeys(terms))
        if not unique_terms or candidate_limit <= 0:
            return []

        total_chunks = await self._count_chunks(include_history)
        if total_chunks == 0:
            return []

        current_filter = [] if include_history else [ChunkModel.is_current.is_(True)]
        average_length_row = await self.session.execute(
            select(func.coalesce(func.avg(ChunkModel.token_count), 0.0)).where(*current_filter)
        )
        average_length = float(average_length_row.scalar_one()) or 1.0

        frequency_rows = await self.session.execute(
            select(
                ChunkNgramModel.gram,
                func.count(func.distinct(ChunkNgramModel.chunk_id)),
            )
            .join(ChunkModel, ChunkNgramModel.chunk_id == ChunkModel.id)
            .where(
                *current_filter,
                ChunkNgramModel.gram.in_(unique_terms),
            )
            .group_by(ChunkNgramModel.gram)
        )
        document_frequency = {str(gram): int(count) for gram, count in frequency_rows.all()}

        candidate_rows = await self.session.execute(
            select(ChunkNgramModel.chunk_id, ChunkModel.source_kind)
            .join(ChunkModel, ChunkNgramModel.chunk_id == ChunkModel.id)
            .where(
                *current_filter,
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

        term_rows = await self.session.execute(
            select(
                ChunkNgramModel.chunk_id,
                ChunkNgramModel.gram,
                ChunkNgramModel.term_frequency,
            ).where(
                ChunkNgramModel.chunk_id.in_(candidate_ids),
                ChunkNgramModel.gram.in_(unique_terms),
            )
        )
        terms_by_chunk: dict[int, dict[str, int]] = {}
        for chunk_id, gram, frequency in term_rows.all():
            terms_by_chunk.setdefault(int(chunk_id), {})[str(gram)] = int(frequency)

        length_rows = await self.session.execute(
            select(ChunkModel.id, ChunkModel.token_count).where(ChunkModel.id.in_(candidate_ids))
        )
        lengths = {int(chunk_id): int(length) for chunk_id, length in length_rows.all()}

        k1 = 1.2
        b = 0.75
        scored: list[TextCandidate] = []
        for chunk_id, frequencies in terms_by_chunk.items():
            document_length = lengths.get(chunk_id, 0)
            score = 0.0
            for gram, term_frequency in frequencies.items():
                doc_frequency = document_frequency.get(gram, 0)
                if doc_frequency == 0:
                    continue
                idf = math.log(1.0 + (total_chunks - doc_frequency + 0.5) / (doc_frequency + 0.5))
                denominator = term_frequency + k1 * (1.0 - b + b * document_length / average_length)
                score += idf * (term_frequency * (k1 + 1.0) / denominator)
            if score > 0:
                scored.append(
                    TextCandidate(
                        chunk_id=chunk_id,
                        source_kind=candidate_kinds[chunk_id],
                        score=score,
                    )
                )
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return scored[:candidate_limit]

    async def vector_candidates(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        scan_limit: int,
        include_history: bool = False,
    ) -> list[VectorCandidate]:
        if not embedding or limit <= 0:
            return []
        statement = select(
            ChunkModel.id,
            ChunkModel.source_kind,
            ChunkModel.embedding,
        ).where(ChunkModel.embedding.is_not(None))
        if not include_history:
            statement = statement.where(ChunkModel.is_current.is_(True))
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
