"""Backend selection for original file bytes.

Both the API and the ingestion worker build one router from Settings. New writes
use the configured backend; reads select the backend persisted on the row, so a
staged migration (for example local to R2, or R2 to RustFS) can serve a mixed
archive.
"""

from __future__ import annotations

from typing import Literal

from app.infrastructure.files.storage_errors import StorageConfigurationError
from app.infrastructure.files.storage_protocol import StorageAdapterProtocol

StorageBackendName = Literal["local", "r2", "s3"]
SUPPORTED_STORAGE_BACKENDS: tuple[StorageBackendName, ...] = ("local", "r2", "s3")
_BACKEND_LABELS: dict[StorageBackendName, str] = {"local": "local", "r2": "R2", "s3": "S3"}


def normalize_backend(value: str | None) -> StorageBackendName:
    """Normalize and validate a backend name from a row or Settings.

    ``rustfs`` is accepted as a configuration alias for ``s3``; rows always
    persist the canonical ``s3`` name.
    """
    candidate = (value or "").strip().lower()
    if candidate == "rustfs":
        candidate = "s3"
    if candidate == "local":
        return "local"
    if candidate == "r2":
        return "r2"
    if candidate == "s3":
        return "s3"
    raise StorageConfigurationError(f"Unsupported storage backend: {candidate or '(empty)'}.")


class StorageRouter:
    """Select the local, R2, or generic S3 adapter for each operation.

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
        s3: StorageAdapterProtocol | None = None,
    ) -> None:
        self._adapters: dict[StorageBackendName, StorageAdapterProtocol | None] = {
            "local": local,
            "r2": r2,
            "s3": s3,
        }
        selected = normalize_backend(default_backend)
        if self._adapters[selected] is None:
            label = _BACKEND_LABELS[selected]
            raise StorageConfigurationError(
                f"The configured storage backend is {selected}, but {label} is not configured."
            )
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
        if self._adapters[selected] is None:
            label = _BACKEND_LABELS[selected]
            raise StorageConfigurationError(f"The {label} storage backend is not configured.")
        return selected

    def take(self, storage_backend: str | None = None) -> StorageAdapterProtocol:
        """Return the adapter for a row value, falling back to the default."""
        selected = self.backend_name(storage_backend)
        adapter = self._adapters[selected]
        if adapter is None:  # pragma: no cover - guarded by backend_name
            raise StorageConfigurationError("The storage backend is not configured.")
        return adapter

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
