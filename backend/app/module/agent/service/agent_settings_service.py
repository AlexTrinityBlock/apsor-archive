"""Database-backed global agent runtime settings.

The settings row is a global singleton. Reads lazily create it with the domain
defaults so a fresh installation has a deterministic config immediately;
``update`` and ``reset`` always write a full, validated snapshot. Only the
root-guarded settings router may mutate it, and normal accounts never receive it
directly. Provider and model selection live in the existing AI settings service,
not here.
"""

from datetime import datetime

from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.model.agent_config_model import AgentConfigModel
from app.module.agent.protocol.agent_config_repository_protocol import (
    AgentConfigRepositoryProtocol,
)
from app.module.agent.schema.settings_schema import (
    AgentSettingsReadSchema,
    AgentSettingsSource,
    AgentSettingsUpdateSchema,
    AgentSettingsValuesSchema,
)
from app.shared.time import utcnow

SINGLETON_ID = 1


class AgentSettingsService:
    """Read, replace, and reset the singleton runtime configuration."""

    def __init__(self, repository: AgentConfigRepositoryProtocol) -> None:
        self.repository = repository

    async def get_settings(self) -> AgentSettingsReadSchema:
        """Return the effective config, creating or repairing the row if needed."""
        config, row, source = await self._effective()
        return _read_schema(config, row, source)

    async def get_runtime_config(self) -> AgentRuntimeConfig:
        """Return an immutable snapshot for one request/run."""
        config, _row, _source = await self._effective()
        return config

    async def update_settings(
        self,
        values: AgentSettingsUpdateSchema,
    ) -> AgentSettingsReadSchema:
        """Replace every stored limit with one validated request payload."""
        config = AgentRuntimeConfig(**values.model_dump())
        row = await self.repository.get_singleton()
        if row is None:
            row = AgentConfigModel(id=SINGLETON_ID)
        _apply_config(row, config, now=utcnow())
        await self.repository.save(row)
        return _read_schema(config, row, "database")

    async def reset_settings(self) -> AgentSettingsReadSchema:
        """Write the domain defaults back to the singleton row."""
        config = AgentRuntimeConfig()
        row = await self.repository.get_singleton()
        if row is None:
            row = AgentConfigModel(id=SINGLETON_ID)
        _apply_config(row, config, now=utcnow())
        await self.repository.save(row)
        return _read_schema(config, row, "database")

    async def _effective(
        self,
    ) -> tuple[AgentRuntimeConfig, AgentConfigModel, AgentSettingsSource]:
        """Load the row, creating defaults or repairing invalid stored values."""
        row = await self.repository.get_singleton()
        if row is None:
            config = AgentRuntimeConfig()
            row = AgentConfigModel(id=SINGLETON_ID)
            _apply_config(row, config, now=utcnow())
            await self.repository.save(row)
            return config, row, "default"
        try:
            return _config_from_model(row), row, "database"
        except ValueError:
            # The table constraints make this unreachable in normal operation,
            # but a manually edited row must not break every agent request.
            config = AgentRuntimeConfig()
            _apply_config(row, config, now=utcnow())
            await self.repository.save(row)
            return config, row, "default"


def _config_from_model(row: AgentConfigModel) -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        compaction_threshold_tokens=row.compaction_threshold_tokens,
        context_window_tokens=row.context_window_tokens,
        max_steps=row.max_steps,
        max_tool_calls_per_turn=row.max_tool_calls_per_turn,
        max_parallel_tools=row.max_parallel_tools,
        max_tool_result_chars=row.max_tool_result_chars,
        max_page_context_chars=row.max_page_context_chars,
        max_compaction_summary_chars=row.max_compaction_summary_chars,
        max_compaction_last_user_chars=row.max_compaction_last_user_chars,
        auto_compaction_enabled=row.auto_compaction_enabled,
        parallel_tools_enabled=row.parallel_tools_enabled,
        save_memory_requires_approval=row.save_memory_requires_approval,
    )


def _apply_config(
    row: AgentConfigModel,
    config: AgentRuntimeConfig,
    *,
    now: datetime,
) -> None:
    row.compaction_threshold_tokens = config.compaction_threshold_tokens
    row.context_window_tokens = config.context_window_tokens
    row.max_steps = config.max_steps
    row.max_tool_calls_per_turn = config.max_tool_calls_per_turn
    row.max_parallel_tools = config.max_parallel_tools
    row.max_tool_result_chars = config.max_tool_result_chars
    row.max_page_context_chars = config.max_page_context_chars
    row.max_compaction_summary_chars = config.max_compaction_summary_chars
    row.max_compaction_last_user_chars = config.max_compaction_last_user_chars
    row.auto_compaction_enabled = config.auto_compaction_enabled
    row.parallel_tools_enabled = config.parallel_tools_enabled
    row.save_memory_requires_approval = config.save_memory_requires_approval
    row.updated_at = now


def _values_schema(config: AgentRuntimeConfig) -> AgentSettingsValuesSchema:
    return AgentSettingsValuesSchema(
        compaction_threshold_tokens=config.compaction_threshold_tokens,
        context_window_tokens=config.context_window_tokens,
        max_steps=config.max_steps,
        max_tool_calls_per_turn=config.max_tool_calls_per_turn,
        max_parallel_tools=config.max_parallel_tools,
        max_tool_result_chars=config.max_tool_result_chars,
        max_page_context_chars=config.max_page_context_chars,
        max_compaction_summary_chars=config.max_compaction_summary_chars,
        max_compaction_last_user_chars=config.max_compaction_last_user_chars,
        auto_compaction_enabled=config.auto_compaction_enabled,
        parallel_tools_enabled=config.parallel_tools_enabled,
        save_memory_requires_approval=config.save_memory_requires_approval,
    )


def _read_schema(
    config: AgentRuntimeConfig,
    row: AgentConfigModel,
    source: AgentSettingsSource,
) -> AgentSettingsReadSchema:
    return AgentSettingsReadSchema(
        config=_values_schema(config),
        defaults=_values_schema(AgentRuntimeConfig()),
        source=source,
        updated_at=row.updated_at,
    )


__all__ = ["AgentSettingsService"]
