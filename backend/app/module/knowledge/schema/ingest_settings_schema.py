"""Request and response contracts for ingestion runtime settings."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

IngestSettingsSource = Literal["database", "default"]


class IngestSettingsValuesSchema(BaseModel):
    """One complete, validated set of ingestion worker settings.

    Every field is required so ``PUT /api/v1/settings/ingest`` always writes a
    full snapshot instead of silently resetting omitted fields to defaults.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    poll_seconds: float = Field(ge=0.25, le=30)
    extract_workers: int = Field(ge=1, le=8)
    max_inflight_jobs: int = Field(ge=1, le=4)
    embedding_concurrency: int = Field(ge=1, le=32)
    chunk_target_chars: int = Field(ge=1_000, le=20_000)
    chunk_overlap_chars: int = Field(ge=0, le=5_000)

    @model_validator(mode="after")
    def _overlap_below_target(self) -> Self:
        """Enforce the invariant a single-field range cannot express."""
        if self.chunk_overlap_chars >= self.chunk_target_chars:
            raise ValueError(
                "chunk_overlap_chars must be less than chunk_target_chars."
            )
        return self


class IngestSettingsUpdateSchema(IngestSettingsValuesSchema):
    """Replace the whole stored worker configuration."""


class IngestSettingsReadSchema(BaseModel):
    """The effective config, the defaults, and where the config came from."""

    model_config = ConfigDict(frozen=True)

    config: IngestSettingsValuesSchema
    defaults: IngestSettingsValuesSchema
    source: IngestSettingsSource
    updated_at: datetime | None


__all__ = [
    "IngestSettingsReadSchema",
    "IngestSettingsSource",
    "IngestSettingsUpdateSchema",
    "IngestSettingsValuesSchema",
]
