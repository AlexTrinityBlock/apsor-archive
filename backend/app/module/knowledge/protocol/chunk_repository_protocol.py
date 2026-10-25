"""Persistence contract for chunks, n-grams, and retrieval candidates."""

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.module.knowledge.model.chunk_model import ChunkModel


class TextCandidate(BaseModel):
    """A BM25 candidate before hydration."""

    model_config = ConfigDict(frozen=True)

    chunk_id: int
    source_kind: str
    score: float


class VectorCandidate(BaseModel):
    """A cosine candidate before hydration."""

    model_config = ConfigDict(frozen=True)

    chunk_id: int
    source_kind: str
    score: float


class ChunkRepositoryProtocol(Protocol):
    async def add(self, chunk: ChunkModel) -> ChunkModel: ...

    async def add_ngrams(self, chunk_id: int, frequencies: dict[str, int]) -> None: ...

    async def mark_source_not_current(self, source_kind: str, source_id: int) -> None: ...

    async def mark_sources_not_current(
        self,
        source_kind: str,
        source_ids: Sequence[int],
    ) -> None: ...

    async def mark_source_current(self, source_kind: str, source_id: int) -> None: ...

    async def delete_source(self, source_kind: str, source_id: int) -> None: ...

    async def get_source_chunks(self, source_kind: str, source_id: int) -> list[ChunkModel]: ...

    async def get_chunk_window(
        self,
        source_kind: str,
        source_id: int,
        start_index: int,
        end_index: int,
    ) -> list[ChunkModel]: ...

    async def get_by_ids(self, chunk_ids: Sequence[int]) -> list[ChunkModel]: ...

    async def text_candidates(
        self,
        terms: Sequence[str],
        *,
        candidate_limit: int,
        include_history: bool = False,
    ) -> list[TextCandidate]: ...

    async def vector_candidates(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        scan_limit: int,
        include_history: bool = False,
    ) -> list[VectorCandidate]: ...

    async def count_current(self) -> int: ...

    async def embedding_model_counts(self) -> dict[str, int]: ...

    async def list_current_chunks(self, *, limit: int, offset: int) -> list[ChunkModel]: ...

    async def update_embedding(
        self,
        chunk_id: int,
        embedding: list[float],
        model: str,
    ) -> None: ...
