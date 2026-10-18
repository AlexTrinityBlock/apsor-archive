"""Schemas for database-backed AI provider settings."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AiPurpose = Literal["chat", "embedding"]
ProviderSource = Literal["database", "environment", "default"]
KeySource = Literal["database", "environment", "none"]


class AiProviderReadSchema(BaseModel):
    """Safe provider state; the API key is never included."""

    model_config = ConfigDict(frozen=True)

    purpose: AiPurpose
    provider: str
    model: str
    base_url: str | None
    dimension: int | None
    enabled: bool
    configured: bool
    key_hint: str | None
    key_source: KeySource
    source: ProviderSource
    updated_at: datetime | None


class AiProviderUpdateSchema(BaseModel):
    """Update one provider; omit ``api_key`` to keep the stored key."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    dimension: int | None = Field(default=None, ge=16, le=4096)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    enabled: bool = True


class AiSettingsReadSchema(BaseModel):
    """Both provider slots plus re-index advice."""

    model_config = ConfigDict(frozen=True)

    chat: AiProviderReadSchema
    embedding: AiProviderReadSchema
    vector_enabled: bool
    reindex_required: bool


class AiTestResultSchema(BaseModel):
    """The outcome of a provider connection test."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    purpose: AiPurpose
    provider: str
    model: str
    latency_ms: int
    detail: str


class EmbeddingReindexSchema(BaseModel):
    """The result of re-embedding the current chunk corpus."""

    model_config = ConfigDict(frozen=True)

    reindexed: int
    model: str
    dimension: int
    elapsed_ms: int
