"""Structural file-storage contract owned by the infrastructure layer.

This mirrors the knowledge slice's ``FileStorageProtocol`` without importing
it, so infrastructure adapters stay independent of any module package. The
knowledge protocol is satisfied structurally.
"""

from typing import Protocol


class StorageAdapterProtocol(Protocol):
    """Persist, retrieve, and delete opaque file bytes."""

    async def save(self, key: str, data: bytes) -> str: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
