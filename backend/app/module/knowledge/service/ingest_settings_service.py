"""Database-backed ingestion runtime settings.

The settings row is a singleton. Reads lazily create it with the environment-
derived defaults so a fresh installation has a deterministic config
immediately; ``update`` and ``reset`` always write a full, validated runtime
snapshot. The two vision prompts are a separate surface: runtime update and
reset never write those columns, so a custom prompt survives a runtime reset.
"""

import hashlib
from datetime import datetime

from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    DEFAULT_VISION_IMAGE_PROMPT,
    VISION_PROMPT_MAX_CHARS,
    VISION_REQUIRED_JSON_KEYS,
    normalize_vision_prompt,
    prompt_warnings,
    validate_vision_prompt,
)
from app.module.knowledge.exception.domain_error import InvalidVisionPromptError
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
from app.module.knowledge.schema.vision_prompt_schema import (
    VisionPromptSettingsReadSchema,
    VisionPromptSettingsUpdateSchema,
    VisionPromptSettingsValuesSchema,
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

    async def peek_runtime_config(self) -> IngestRuntimeConfig:
        """Return the stored snapshot without creating or repairing the row.

        Uploads use this read-only view so an absent ``ingest_config`` row is
        left for the settings API to create on its first read.
        """
        row = await self.repository.get_singleton()
        if row is None:
            return self.defaults
        try:
            return _config_from_model(row)
        except ValueError:
            return self.defaults

    async def get_vision_prompts(self) -> VisionPromptSettingsReadSchema:
        """Return the effective prompts, defaults, fingerprints, and warnings."""
        config, row, _source = await self._effective()
        return _vision_prompt_read_schema(config, row, self.defaults)

    async def update_vision_prompts(
        self,
        values: VisionPromptSettingsUpdateSchema,
    ) -> VisionPromptSettingsReadSchema:
        """Validate and store both templates without touching runtime settings."""
        image_prompt = _validated_prompt(values.image_prompt)
        document_prompt = _validated_prompt(values.document_prompt)
        row = await self.repository.get_singleton()
        if row is None:
            row = IngestConfigModel(id=SINGLETON_ID)
        _apply_prompts(
            row,
            image_prompt=image_prompt,
            document_prompt=document_prompt,
            now=utcnow(),
        )
        await self.repository.save(row)
        config = _config_from_model(row)
        return _vision_prompt_read_schema(config, row, self.defaults)

    async def update_settings(
        self,
        values: IngestSettingsUpdateSchema,
    ) -> IngestSettingsReadSchema:
        """Replace every stored runtime setting with one validated payload."""
        config = IngestRuntimeConfig(**values.model_dump())
        row = await self.repository.get_singleton()
        if row is None:
            row = IngestConfigModel(id=SINGLETON_ID)
        _apply_config(row, config, now=utcnow())
        await self.repository.save(row)
        return _read_schema(config, row, "database", self.defaults)

    async def reset_settings(self) -> IngestSettingsReadSchema:
        """Write the environment-seeded runtime defaults back to the row.

        The prompt columns are deliberately left untouched.
        """
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


def _validated_prompt(value: str) -> str:
    try:
        normalized = normalize_vision_prompt(value)
        validate_vision_prompt(normalized)
    except ValueError as exc:
        raise InvalidVisionPromptError(str(exc)) from exc
    return normalized


def _normalized_prompt_or_default(value: str | None, default: str) -> str:
    if value is None:
        return default
    try:
        normalized = normalize_vision_prompt(value)
        validate_vision_prompt(normalized)
    except ValueError:
        return default
    return normalized


def _config_from_model(row: IngestConfigModel) -> IngestRuntimeConfig:
    return IngestRuntimeConfig(
        poll_seconds=row.poll_seconds,
        extract_workers=row.extract_workers,
        max_inflight_jobs=row.max_inflight_jobs,
        embedding_concurrency=row.embedding_concurrency,
        chunk_target_chars=row.chunk_target_chars,
        chunk_overlap_chars=row.chunk_overlap_chars,
        vision_description_language=row.vision_description_language,
        vision_image_prompt=_normalized_prompt_or_default(
            row.vision_image_prompt,
            DEFAULT_VISION_IMAGE_PROMPT,
        ),
        vision_document_prompt=_normalized_prompt_or_default(
            row.vision_document_prompt,
            DEFAULT_VISION_DOCUMENT_PROMPT,
        ),
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
    row.vision_description_language = config.vision_description_language
    row.updated_at = now


def _apply_prompts(
    row: IngestConfigModel,
    *,
    image_prompt: str,
    document_prompt: str,
    now: datetime,
) -> None:
    row.vision_image_prompt = image_prompt
    row.vision_document_prompt = document_prompt
    row.updated_at = now


def _values_schema(config: IngestRuntimeConfig) -> IngestSettingsValuesSchema:
    return IngestSettingsValuesSchema(
        poll_seconds=config.poll_seconds,
        extract_workers=config.extract_workers,
        max_inflight_jobs=config.max_inflight_jobs,
        embedding_concurrency=config.embedding_concurrency,
        chunk_target_chars=config.chunk_target_chars,
        chunk_overlap_chars=config.chunk_overlap_chars,
        vision_description_language=config.vision_description_language,
    )


def _prompt_values_schema(config: IngestRuntimeConfig) -> VisionPromptSettingsValuesSchema:
    return VisionPromptSettingsValuesSchema(
        image_prompt=config.vision_image_prompt,
        document_prompt=config.vision_document_prompt,
    )


def _prompt_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _vision_prompt_read_schema(
    config: IngestRuntimeConfig,
    row: IngestConfigModel,
    defaults: IngestRuntimeConfig,
) -> VisionPromptSettingsReadSchema:
    warnings = sorted(
        {
            *prompt_warnings(config.vision_image_prompt),
            *prompt_warnings(config.vision_document_prompt),
        }
    )
    source: IngestSettingsSource = (
        "database"
        if row.vision_image_prompt is not None or row.vision_document_prompt is not None
        else "default"
    )
    return VisionPromptSettingsReadSchema(
        config=_prompt_values_schema(config),
        defaults=_prompt_values_schema(defaults),
        source=source,
        updated_at=row.updated_at,
        max_chars=VISION_PROMPT_MAX_CHARS,
        required_keys=VISION_REQUIRED_JSON_KEYS,
        image_prompt_sha256=_prompt_sha256(config.vision_image_prompt),
        document_prompt_sha256=_prompt_sha256(config.vision_document_prompt),
        warnings=warnings,
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
