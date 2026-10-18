"""Storage contract for original media bytes."""

from typing import Protocol


class MediaStorageProtocol(Protocol):
    async def save(self, key: str, data: bytes) -> str: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
