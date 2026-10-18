"""SQLAlchemy persistence for standalone media retrieval."""

import math
from collections.abc import Sequence

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.media.domain.visual_domain import cosine_similarity
from app.module.media.model.media_model import MediaModel, MediaNgramModel
from app.module.media.protocol.media_repository_protocol import (
    MediaTextCandidate,
    MediaVisualCandidate,
)
from app.shared.time import utcnow


class MediaRepository:
    """BM25 over captions/tags and cosine over visual descriptors."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, media: MediaModel) -> MediaModel:
        self.session.add(media)
        await self.session.flush()
        return media

    async def save(self, media: MediaModel) -> MediaModel:
        media.updated_at = utcnow()
        self.session.add(media)
        await self.session.flush()
        return media

    async def add_ngrams(self, media_id: int, frequencies: dict[str, int]) -> None:
        if not frequencies:
            return
        rows = [
            {"media_id": media_id, "gram": gram, "term_frequency": frequency}
            for gram, frequency in frequencies.items()
        ]
        await self.session.execute(insert(MediaNgramModel), rows)

    async def replace_ngrams(self, media_id: int, frequencies: dict[str, int]) -> None:
        await self.session.execute(
            delete(MediaNgramModel).where(MediaNgramModel.media_id == media_id)
        )
        await self.add_ngrams(media_id, frequencies)

    async def get_by_id(self, media_id: int) -> MediaModel | None:
        return await self.session.get(MediaModel, media_id)

    async def get_current_by_path(self, path: str) -> MediaModel | None:
        statement = select(MediaModel).where(
            MediaModel.raw_file_path == path,
            MediaModel.is_current.is_(True),
            MediaModel.deleted_at.is_(None),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def mark_not_current(self, media: MediaModel) -> None:
        media.is_current = False
        media.updated_at = utcnow()
        self.session.add(media)
        await self.session.flush()

    async def list_by_ids(self, media_ids: Sequence[int]) -> list[MediaModel]:
        if not media_ids:
            return []
        statement = select(MediaModel).where(MediaModel.id.in_(media_ids))
        return list((await self.session.execute(statement)).scalars().all())

    async def list_recent(self, *, limit: int, offset: int) -> list[MediaModel]:
        statement = (
            select(MediaModel)
            .where(MediaModel.is_current.is_(True), MediaModel.deleted_at.is_(None))
            .order_by(MediaModel.created_at.desc(), MediaModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count(self) -> int:
        statement = select(func.count(MediaModel.id)).where(
            MediaModel.is_current.is_(True),
            MediaModel.deleted_at.is_(None),
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def text_candidates(
        self,
        terms: Sequence[str],
        *,
        limit: int,
    ) -> list[MediaTextCandidate]:
        unique_terms = list(dict.fromkeys(terms))
        if not unique_terms or limit <= 0:
            return []
        current = [
            MediaModel.is_current.is_(True),
            MediaModel.deleted_at.is_(None),
        ]
        total_media = await self.count()
        if total_media == 0:
            return []

        average_length = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.avg(MediaModel.token_count), 0.0)).where(
                        *current
                    )
                )
            ).scalar_one()
        ) or 1.0

        document_frequency = {
            str(gram): int(count)
            for gram, count in (
                await self.session.execute(
                    select(
                        MediaNgramModel.gram,
                        func.count(func.distinct(MediaNgramModel.media_id)),
                    )
                    .join(MediaModel, MediaNgramModel.media_id == MediaModel.id)
                    .where(*current, MediaNgramModel.gram.in_(unique_terms))
                    .group_by(MediaNgramModel.gram)
                )
            ).all()
        }

        candidate_ids = [
            int(row[0])
            for row in (
                await self.session.execute(
                    select(MediaNgramModel.media_id)
                    .join(MediaModel, MediaNgramModel.media_id == MediaModel.id)
                    .where(*current, MediaNgramModel.gram.in_(unique_terms))
                    .group_by(MediaNgramModel.media_id)
                    .order_by(func.sum(MediaNgramModel.term_frequency).desc())
                    .limit(limit)
                )
            ).all()
        ]
        if not candidate_ids:
            return []

        terms_by_media: dict[int, dict[str, int]] = {}
        for media_id, gram, frequency in (
            await self.session.execute(
                select(
                    MediaNgramModel.media_id,
                    MediaNgramModel.gram,
                    MediaNgramModel.term_frequency,
                ).where(
                    MediaNgramModel.media_id.in_(candidate_ids),
                    MediaNgramModel.gram.in_(unique_terms),
                )
            )
        ).all():
            terms_by_media.setdefault(int(media_id), {})[str(gram)] = int(frequency)

        lengths = {
            int(media_id): int(length)
            for media_id, length in (
                await self.session.execute(
                    select(MediaModel.id, MediaModel.token_count).where(
                        MediaModel.id.in_(candidate_ids)
                    )
                )
            ).all()
        }

        k1 = 1.2
        b = 0.75
        scored: list[MediaTextCandidate] = []
        for media_id, frequencies in terms_by_media.items():
            document_length = lengths.get(media_id, 0)
            score = 0.0
            for gram, term_frequency in frequencies.items():
                doc_frequency = document_frequency.get(gram, 0)
                if doc_frequency == 0:
                    continue
                idf = math.log(
                    1.0 + (total_media - doc_frequency + 0.5) / (doc_frequency + 0.5)
                )
                denominator = term_frequency + k1 * (
                    1.0 - b + b * document_length / average_length
                )
                score += idf * (term_frequency * (k1 + 1.0) / denominator)
            if score > 0:
                scored.append(MediaTextCandidate(media_id=media_id, score=score))
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return scored[:limit]

    async def visual_candidates(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
    ) -> list[MediaVisualCandidate]:
        if not embedding or limit <= 0:
            return []
        rows = await self.session.execute(
            select(MediaModel.id, MediaModel.visual_embedding).where(
                MediaModel.is_current.is_(True),
                MediaModel.deleted_at.is_(None),
                MediaModel.visual_embedding.is_not(None),
            )
        )
        query = [float(value) for value in embedding]
        scored: list[MediaVisualCandidate] = []
        for media_id, raw in rows.all():
            if not isinstance(raw, list):
                continue
            score = cosine_similarity(query, [float(value) for value in raw])
            scored.append(MediaVisualCandidate(media_id=int(media_id), score=score))
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return scored[:limit]
