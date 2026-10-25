"""HTTP schemas for the unified provider registry.

No schema in this module contains a plaintext API key.  ``api_key_hint`` and
``key_hint`` are the only key-derived values that may cross the HTTP boundary.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderCapability = Literal["chat", "embedding", "web_search", "web_fetch"]
KeySource = Literal["database", "environment", "none"]
ProviderSource = Literal["database", "environment", "default"]


class ProviderReadSchema(BaseModel):
    """Safe provider state; the API key is never included."""

    model_config = ConfigDict(frozen=True)

    id: int | None
    capability: ProviderCapability
    provider: str
    label: str
    model: str | None
    base_url: str | None
    dimension: int | None
    is_active: bool
    configured: bool
    key_hint: str | None
    key_source: KeySource
    source: ProviderSource
    updated_at: datetime | None


class ProviderCapabilityReadSchema(BaseModel):
    """One capability group in the registry UI."""

    model_config = ConfigDict(frozen=True)

    capability: ProviderCapability
    title: str
    description: str
    allowed_providers: list[str]
    keyless_providers: list[str]
    default_base_url: str | None
    supports_model: bool
    supports_dimension: bool
    active: ProviderReadSchema | None
    providers: list[ProviderReadSchema]


class ProviderRegistryReadSchema(BaseModel):
    """The complete registry plus vector/re-index advice."""

    model_config = ConfigDict(frozen=True)

    capabilities: list[ProviderCapabilityReadSchema]
    vector_enabled: bool
    reindex_required: bool


class ProviderCreateSchema(BaseModel):
    """Create one provider row; activate it immediately by default."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    label: str = Field(default="", max_length=80)
    model: str | None = Field(default=None, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    dimension: int | None = Field(default=None, ge=16, le=4096)
    api_key: str | None = Field(default=None, max_length=500)
    activate: bool = True


class ProviderUpdateSchema(BaseModel):
    """Full replacement of one provider row.

    Omit ``api_key`` to keep the stored key; set ``clear_api_key`` to remove it.
    ``activate`` defaults to ``False`` so editing an inactive saved provider
    never silently makes it the active one; activation must be explicit.  When
    ``activate`` is false the row keeps its current active state.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=32)
    label: str = Field(default="", max_length=80)
    model: str | None = Field(default=None, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    dimension: int | None = Field(default=None, ge=16, le=4096)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    activate: bool = False


class ProviderTestResultSchema(BaseModel):
    """The outcome of one provider connection test."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    capability: ProviderCapability
    provider_id: int
    provider: str
    label: str
    latency_ms: int
    detail: str


__all__ = [
    "KeySource",
    "ProviderCapability",
    "ProviderCapabilityReadSchema",
    "ProviderCreateSchema",
    "ProviderReadSchema",
    "ProviderRegistryReadSchema",
    "ProviderSource",
    "ProviderTestResultSchema",
    "ProviderUpdateSchema",
]
