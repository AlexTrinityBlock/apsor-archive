"""Persistence contract for file thumbnails."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ThumbnailMeta:
    """A ready thumbnail's size and hash, without its bytes."""

    file_id: int
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class ThumbnailBytes:
    """A ready thumbnail's bytes and hash."""

    data: bytes
    sha256: str


class FileThumbnailRepositoryProtocol(Protocol):
    async def upsert(
        self,
        *,
        file_id: int,
        status: str,
        data: bytes | None,
        width: int | None,
        height: int | None,
        sha256: str | None,
        generator_version: int,
        error_code: str | None,
    ) -> None: ...

    async def get_ready(self, file_id: int) -> ThumbnailBytes | None: ...

    async def meta_for(self, file_ids: Sequence[int]) -> dict[int, ThumbnailMeta]: ...

    async def find_reusable(
        self,
        *,
        content_hash: str,
        extension: str,
        generator_version: int,
        exclude_file_id: int,
    ) -> int | None: ...

    async def clone(self, *, source_file_id: int, target_file_id: int) -> bool: ...
