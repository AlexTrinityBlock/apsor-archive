"""HTTP contracts for account model assignments and chat endpoints.

No schema in this module carries key material. Endpoint rows expose a host name
only (never the full base URL) and a ``key_source`` derived from the stored
ciphertext or the provider-scoped environment key. Assignments expose the
stored columns, their effective resolution, and advisory warnings.
"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ModelAssignmentSource = Literal["account", "unassigned"]
EndpointKeySource = Literal["database", "environment", "none"]
ProbePurpose = Literal["primary", "auxiliary"]


class ModelPricingSchema(BaseModel):
    """USD per million tokens; ``cache_write`` is the five-minute write bucket."""

    model_config = ConfigDict(frozen=True)

    input: float
    output: float
    cache_write: float
    cache_read: float


class ModelAssignmentUpdateSchema(BaseModel):
    """Full replacement of one account's two endpoint assignments.

    ``PUT`` requires both slots. The primary effort may be empty (the provider
    default applies); the auxiliary effort is required and defaults to ``low``.
    Budget ranges match the database CHECKs. The cross-field rule
    ``compaction_threshold_tokens < context_window_tokens`` is enforced by the
    service so a violation keeps the documented ``422
    invalid_model_assignment`` code instead of the request-validation ``400``.
    """

    model_config = ConfigDict(extra="forbid")

    chat_provider_config_id: int = Field(gt=0)
    chat_model: str = Field(min_length=1, max_length=128)
    chat_reasoning_effort: str | None = Field(default=None, max_length=32)
    aux_provider_config_id: int = Field(gt=0)
    aux_model: str = Field(min_length=1, max_length=128)
    aux_reasoning_effort: str | None = Field(default=None, max_length=32)
    context_window_tokens: int | None = Field(default=None, ge=8_000, le=2_000_000)
    compaction_threshold_tokens: int | None = Field(
        default=None,
        ge=1_000,
        le=1_000_000,
    )

    @field_validator("chat_model", "aux_model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        """Accept any non-blank string verbatim; the catalog never validates it."""
        if not value.strip():
            raise ValueError("model must contain at least one non-whitespace character.")
        return value

    @field_validator("chat_reasoning_effort")
    @classmethod
    def _normalize_primary_effort(cls, value: str | None) -> str | None:
        """Trim the primary effort and treat an empty value as "omit the field"."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 32:
            raise ValueError("chat_reasoning_effort must be at most 32 characters.")
        return trimmed

    @field_validator("aux_reasoning_effort")
    @classmethod
    def _normalize_auxiliary_effort(cls, value: str | None) -> str | None:
        """Trim the auxiliary effort; empty means "omit the field" like the primary."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 32:
            raise ValueError("aux_reasoning_effort must be at most 32 characters.")
        return trimmed


class ModelAssignmentSchema(BaseModel):
    """One account assignment: stored values, effective resolution, warnings."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    username: str
    chat_provider_config_id: int | None
    chat_model: str | None
    chat_reasoning_effort: str | None
    aux_provider_config_id: int | None
    aux_model: str | None
    aux_reasoning_effort: str | None
    chat_context_window_tokens: int | None
    chat_compaction_threshold_tokens: int | None
    chat_provider_label: str | None
    aux_provider_label: str | None
    effective_chat_model: str | None
    effective_chat_provider: str
    effective_chat_effort: str | None
    effective_aux_model: str | None
    effective_aux_provider: str
    effective_aux_effort: str | None
    effective_context_window_tokens: int | None
    effective_compaction_threshold_tokens: int | None
    chat_tier: str | None
    aux_tier: str | None
    chat_pricing: ModelPricingSchema | None
    aux_pricing: ModelPricingSchema | None
    source: ModelAssignmentSource
    degraded_reason: str | None
    warnings: list[str]
    updated_at: datetime


class ModelAssignmentListSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ModelAssignmentSchema]


class ChatEndpointSchema(BaseModel):
    """One saved chat endpoint without key material or a full base URL."""

    model_config = ConfigDict(frozen=True)

    id: int
    label: str
    provider: str
    model: str | None
    base_url_host: str | None
    configured: bool
    key_source: EndpointKeySource
    is_active: bool
    priority: int
    max_output_tokens: int | None


class ChatEndpointListSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ChatEndpointSchema]


class ModelCatalogEntrySchema(BaseModel):
    """One advisory catalog row; unknown models are legal and unpriced."""

    model_config = ConfigDict(frozen=True)

    model: str
    display_name: str
    provider: str
    tier: str | None
    context_window_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    pricing: ModelPricingSchema | None
    suggested_compaction_tokens: int | None
    status: str
    replacement_model: str | None


class ModelCatalogListSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ModelCatalogEntrySchema]


class ChatEndpointProbeSchema(BaseModel):
    """One candidate ``(model, effort)`` pair to test against a saved row."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=128)
    reasoning_effort: str | None = Field(default=None, max_length=32)
    purpose: ProbePurpose = "primary"

    @field_validator("model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must contain at least one non-whitespace character.")
        return value

    @field_validator("reasoning_effort")
    @classmethod
    def _normalize_effort(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 32:
            raise ValueError("reasoning_effort must be at most 32 characters.")
        return trimmed

    @model_validator(mode="after")
    def _auxiliary_requires_effort(self) -> Self:
        """An auxiliary call always sends an effort; empty is primary-only."""
        if self.purpose == "auxiliary" and not self.reasoning_effort:
            raise ValueError("reasoning_effort is required for an auxiliary probe.")
        return self


class ChatEndpointProbeResultSchema(BaseModel):
    """A probe always resolves to this shape; a failure is not an HTTP error."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    latency_ms: int
    resolved_model: str | None
    usage: dict[str, int]
    detail: str | None


__all__ = [
    "ChatEndpointListSchema",
    "ChatEndpointProbeResultSchema",
    "ChatEndpointProbeSchema",
    "ChatEndpointSchema",
    "EndpointKeySource",
    "ModelAssignmentListSchema",
    "ModelAssignmentSchema",
    "ModelAssignmentSource",
    "ModelAssignmentUpdateSchema",
    "ModelCatalogEntrySchema",
    "ModelCatalogListSchema",
    "ModelPricingSchema",
    "ProbePurpose",
]
