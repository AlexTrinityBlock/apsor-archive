"""Request and response contracts for agent runtime settings."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentSettingsSource = Literal["database", "default"]


class AgentSettingsValuesSchema(BaseModel):
    """One complete, validated set of agent runtime limits.

    Every field is required so ``PUT /api/v1/agent/settings`` always writes a
    full snapshot instead of silently resetting omitted fields to defaults.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_total_tokens: int = Field(ge=8_000, le=200_000)
    compaction_threshold_tokens: int = Field(ge=1_000, le=200_000)
    max_steps: int = Field(ge=1, le=32)
    max_tool_calls_per_turn: int = Field(ge=1, le=24)
    max_parallel_tools: int = Field(ge=1, le=24)
    max_tool_result_chars: int = Field(ge=1_000, le=100_000)
    max_page_context_chars: int = Field(ge=500, le=50_000)
    max_compaction_summary_chars: int = Field(ge=1_000, le=20_000)
    max_compaction_last_user_chars: int = Field(ge=500, le=10_000)
    auto_compaction_enabled: bool
    parallel_tools_enabled: bool

    @model_validator(mode="after")
    def _cross_field_ranges(self) -> Self:
        """Enforce the invariants a single-field range cannot express."""
        if self.compaction_threshold_tokens >= self.max_total_tokens:
            raise ValueError(
                "compaction_threshold_tokens must be less than max_total_tokens."
            )
        if self.max_parallel_tools > self.max_tool_calls_per_turn:
            raise ValueError(
                "max_parallel_tools must not exceed max_tool_calls_per_turn."
            )
        return self


class AgentSettingsUpdateSchema(AgentSettingsValuesSchema):
    """Replace the whole stored runtime configuration."""


class AgentSettingsReadSchema(BaseModel):
    """The effective config, the defaults, and where the config came from."""

    model_config = ConfigDict(frozen=True)

    config: AgentSettingsValuesSchema
    defaults: AgentSettingsValuesSchema
    source: AgentSettingsSource
    updated_at: datetime | None


__all__ = [
    "AgentSettingsReadSchema",
    "AgentSettingsSource",
    "AgentSettingsUpdateSchema",
    "AgentSettingsValuesSchema",
]
