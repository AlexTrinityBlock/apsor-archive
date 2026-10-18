"""Cache contract for the media slice."""

from typing import Protocol


class MediaCacheProtocol(Protocol):
    async def bump_version(self) -> int: ...
