"""Pure contract for storing original file bytes.

The application-level implementation is a backend router: new writes go to the
configured default backend, while reads and deletes select the backend that was
persisted on the file or ingestion-job row.
"""

from typing import Protocol


class FileStorageProtocol(Protocol):
    """Persist and retrieve opaque file bytes on a selectable backend."""

    @property
    def default_backend(self) -> str:
        """Backend name to persist with a new write."""
        ...

    def backend_name(self, storage_backend: str | None = None) -> str:
        """Resolve a stored backend name, falling back to the default."""
        ...

    async def save(
        self,
        key: str,
        data: bytes,
        *,
        backend: str | None = None,
    ) -> str: ...

    async def read(self, key: str, *, backend: str | None = None) -> bytes: ...

    async def delete(self, key: str, *, backend: str | None = None) -> None: ...
