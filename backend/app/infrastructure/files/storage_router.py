"""Backend selection for original file bytes.

Both the API and the ingestion worker build one router from Settings. New writes
use the configured backend; reads can select the backend persisted on the row so
a staged local-to-R2 migration can serve a mixed archive.
"""

from __future__ import annotations

from typing import Literal

from app.infrastructure.files.storage_errors import StorageConfigurationError
from app.infrastructure.files.storage_protocol import StorageAdapterProtocol

StorageBackendName = Literal["local", "r2"]
SUPPORTED_STORAGE_BACKENDS: tuple[StorageBackendName, ...] = ("local", "r2")


def normalize_backend(value: str | None) -> StorageBackendName:
    """Normalize and validate a backend name from a row or Settings."""
    candidate = (value or "").strip().lower()
    if candidate not in SUPPORTED_STORAGE_BACKENDS:
        raise StorageConfigurationError(f"Unsupported storage backend: {candidate or '(empty)'}.")
    return candidate


class StorageRouter:
    """Select the local or R2 adapter for each operation.

    ``take(backend)`` and the optional ``backend`` keyword accept a row's
    ``storage_backend``. ``None`` means "use the configured default", which is
    how legacy rows with a null backend are read.
    """

    def __init__(
        self,
        *,
        local: StorageAdapterProtocol,
        r2: StorageAdapterProtocol | None,
        default_backend: str,
    ) -> None:
        selected = normalize_backend(default_backend)
        if selected == "r2" and r2 is None:
            raise StorageConfigurationError(
                "The configured storage backend is r2, but R2 is not configured."
            )
        self._local = local
        self._r2 = r2
        self._default_backend = selected

    @property
    def default_backend(self) -> StorageBackendName:
        """Backend to persist with a new write."""
        return self._default_backend

    def backend_name(self, storage_backend: str | None = None) -> StorageBackendName:
        """Resolve a row value to a usable backend name."""
        selected = (
            self._default_backend if storage_backend is None else normalize_backend(storage_backend)
        )
        if selected == "r2" and self._r2 is None:
            raise StorageConfigurationError("The R2 storage backend is not configured.")
        return selected

    def take(self, storage_backend: str | None = None) -> StorageAdapterProtocol:
        """Return the adapter for a row value, falling back to the default."""
        selected = self.backend_name(storage_backend)
        if selected == "local":
            return self._local
        if self._r2 is None:  # pragma: no cover - guarded by backend_name
            raise StorageConfigurationError("The R2 storage backend is not configured.")
        return self._r2

    def adapter_for(self, storage_backend: str | None = None) -> StorageAdapterProtocol:
        """Alias for ``take`` with a more explicit name."""
        return self.take(storage_backend)

    async def save(
        self,
        key: str,
        data: bytes,
        *,
        backend: str | None = None,
    ) -> str:
        return await self.take(backend).save(key, data)

    async def read(self, key: str, *, backend: str | None = None) -> bytes:
        return await self.take(backend).read(key)

    async def delete(self, key: str, *, backend: str | None = None) -> None:
        await self.take(backend).delete(key)


__all__ = [
    "SUPPORTED_STORAGE_BACKENDS",
    "StorageBackendName",
    "StorageRouter",
    "normalize_backend",
]
