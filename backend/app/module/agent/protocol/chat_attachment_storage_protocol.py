"""Object-storage contract used by temporary chat images."""

from typing import Protocol


class ChatAttachmentStorageProtocol(Protocol):
    """Persist, retrieve, and delete opaque bytes on a selectable backend."""

    @property
    def default_backend(self) -> str: ...

    async def save(self, key: str, data: bytes, *, backend: str | None = None) -> str: ...

    async def read(self, key: str, *, backend: str | None = None) -> bytes: ...

    async def delete(self, key: str, *, backend: str | None = None) -> None: ...


__all__ = ["ChatAttachmentStorageProtocol"]
