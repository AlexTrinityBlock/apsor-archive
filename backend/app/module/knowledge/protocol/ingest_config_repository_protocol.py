"""Consumer-owned persistence contract for the singleton ingest config."""

from typing import Protocol

from app.module.knowledge.model.ingest_config_model import IngestConfigModel


class IngestConfigRepositoryProtocol(Protocol):
    """Read and persist the one row that owns the worker settings."""

    async def get_singleton(self) -> IngestConfigModel | None: ...

    async def save(self, config: IngestConfigModel) -> IngestConfigModel: ...


__all__ = ["IngestConfigRepositoryProtocol"]
