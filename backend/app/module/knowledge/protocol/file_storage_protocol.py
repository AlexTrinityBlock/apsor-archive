"""Pure contract for storing original file bytes."""

from typing import Protocol


class FileStorageProtocol(Protocol):
    """Persist and retrieve opaque file bytes."""

    async def save(self, key: str, data: bytes) -> str: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
