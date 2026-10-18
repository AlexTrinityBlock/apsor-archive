"""Media persistence contracts."""

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.module.media.model.media_model import MediaModel


class MediaTextCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_id: int
    score: float


class MediaVisualCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_id: int
    score: float


class MediaRepositoryProtocol(Protocol):
    async def add(self, media: MediaModel) -> MediaModel: ...

    async def save(self, media: MediaModel) -> MediaModel: ...

    async def add_ngrams(self, media_id: int, frequencies: dict[str, int]) -> None: ...

    async def replace_ngrams(self, media_id: int, frequencies: dict[str, int]) -> None: ...

    async def get_by_id(self, media_id: int) -> MediaModel | None: ...

    async def get_current_by_path(self, path: str) -> MediaModel | None: ...

    async def mark_not_current(self, media: MediaModel) -> None: ...

    async def list_by_ids(self, media_ids: Sequence[int]) -> list[MediaModel]: ...

    async def list_recent(self, *, limit: int, offset: int) -> list[MediaModel]: ...

    async def count(self) -> int: ...

    async def text_candidates(
        self,
        terms: Sequence[str],
        *,
        limit: int,
    ) -> list[MediaTextCandidate]: ...

    async def visual_candidates(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
    ) -> list[MediaVisualCandidate]: ...
