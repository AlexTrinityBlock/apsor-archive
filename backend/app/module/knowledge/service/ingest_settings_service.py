"""Database-backed ingestion runtime settings.

The settings row is a singleton. Reads lazily create it with the environment-
derived defaults so a fresh installation has a deterministic config
immediately; ``update`` and ``reset`` always write a full, validated snapshot.
"""

from datetime import datetime

from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.model.ingest_config_model import IngestConfigModel
from app.module.knowledge.protocol.ingest_config_repository_protocol import (
    IngestConfigRepositoryProtocol,
)
from app.module.knowledge.schema.ingest_settings_schema import (
    IngestSettingsReadSchema,
    IngestSettingsSource,
    IngestSettingsUpdateSchema,
    IngestSettingsValuesSchema,
)
from app.shared.time import utcnow

SINGLETON_ID = 1


class IngestSettingsService:
    """Read, replace, and reset the singleton runtime configuration."""

    def __init__(
        self,
        repository: IngestConfigRepositoryProtocol,
        defaults: IngestRuntimeConfig | None = None,
    ) -> None:
        self.repository = repository
        self.defaults = defaults or IngestRuntimeConfig()

    async def get_settings(self) -> IngestSettingsReadSchema:
        """Return the effective config, creating or repairing the row if needed."""
        config, row, source = await self._effective()
        return _read_schema(config, row, source, self.defaults)

    async def get_runtime_config(self) -> IngestRuntimeConfig:
        """Return an immutable snapshot for one worker loop or job."""
        config, _row, _source = await self._effective()
        return config

    async def update_settings(
        self,
        values: IngestSettingsUpdateSchema,
    ) -> IngestSettingsReadSchema:
        """Replace every stored setting with one validated request payload."""
        config = IngestRuntimeConfig(**values.model_dump())
        row = await self.repository.get_singleton()
        if row is None:
            row = IngestConfigModel(id=SINGLETON_ID)
        _apply_config(row, config, now=utcnow())
        await self.repository.save(row)
        return _read_schema(config, row, "database", self.defaults)

    async def reset_settings(self) -> IngestSettingsReadSchema:
        """Write the environment-seeded defaults back to the singleton row."""
        config = self.defaults
        row = await self.repository.get_singleton()
        if row is None:
            row = IngestConfigModel(id=SINGLETON_ID)
        _apply_config(row, config, now=utcnow())
        await self.repository.save(row)
        return _read_schema(config, row, "database", self.defaults)

    async def _effective(
        self,
    ) -> tuple[IngestRuntimeConfig, IngestConfigModel, IngestSettingsSource]:
        """Load the row, creating defaults or repairing invalid stored values."""
        row = await self.repository.get_singleton()
        if row is None:
            config = self.defaults
            row = IngestConfigModel(id=SINGLETON_ID)
            _apply_config(row, config, now=utcnow())
            await self.repository.save(row)
            return config, row, "default"
        try:
            return _config_from_model(row), row, "database"
        except ValueError:
            # The table constraints make this unreachable in normal operation,
            # but a manually edited row must not break the worker forever.
            config = self.defaults
            _apply_config(row, config, now=utcnow())
            await self.repository.save(row)
            return config, row, "default"


def _config_from_model(row: IngestConfigModel) -> IngestRuntimeConfig:
    return IngestRuntimeConfig(
        poll_seconds=row.poll_seconds,
        extract_workers=row.extract_workers,
        max_inflight_jobs=row.max_inflight_jobs,
        embedding_concurrency=row.embedding_concurrency,
        chunk_target_chars=row.chunk_target_chars,
        chunk_overlap_chars=row.chunk_overlap_chars,
    )


def _apply_config(
    row: IngestConfigModel,
    config: IngestRuntimeConfig,
    *,
    now: datetime,
) -> None:
    row.poll_seconds = config.poll_seconds
    row.extract_workers = config.extract_workers
    row.max_inflight_jobs = config.max_inflight_jobs
    row.embedding_concurrency = config.embedding_concurrency
    row.chunk_target_chars = config.chunk_target_chars
    row.chunk_overlap_chars = config.chunk_overlap_chars
    row.updated_at = now


def _values_schema(config: IngestRuntimeConfig) -> IngestSettingsValuesSchema:
    return IngestSettingsValuesSchema(
        poll_seconds=config.poll_seconds,
        extract_workers=config.extract_workers,
        max_inflight_jobs=config.max_inflight_jobs,
        embedding_concurrency=config.embedding_concurrency,
        chunk_target_chars=config.chunk_target_chars,
        chunk_overlap_chars=config.chunk_overlap_chars,
    )


def _read_schema(
    config: IngestRuntimeConfig,
    row: IngestConfigModel,
    source: IngestSettingsSource,
    defaults: IngestRuntimeConfig,
) -> IngestSettingsReadSchema:
    return IngestSettingsReadSchema(
        config=_values_schema(config),
        defaults=_values_schema(defaults),
        source=source,
        updated_at=row.updated_at,
    )


__all__ = ["IngestSettingsService"]
