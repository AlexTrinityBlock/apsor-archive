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
from app.module.agent.exception.domain_error import AgentInvalidCompactionPromptError
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
        """Replace every stored limit with one validated request payload.

        The schema enforces the numeric bounds; the domain re-validates the
        compaction template. A template without ``{max_output_tokens}``, with an
        unknown placeholder, or with a stray brace becomes
        ``compaction_prompt_invalid`` rather than a generic validation error.
        """
        try:
            config = AgentRuntimeConfig(**values.model_dump())
        except ValueError as exc:
            if "compaction_prompt" in str(exc):
                raise AgentInvalidCompactionPromptError(str(exc)) from exc
            raise
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
        max_parallel_tools=row.max_parallel_tools,
        max_tool_result_chars=row.max_tool_result_chars,
        max_page_context_chars=row.max_page_context_chars,
        max_compaction_summary_chars=row.max_compaction_summary_chars,
        max_compaction_last_user_chars=row.max_compaction_last_user_chars,
        model_escalation_enabled=row.model_escalation_enabled,
        compaction_prompt=row.compaction_prompt,
        compaction_max_output_tokens=row.compaction_max_output_tokens,
        agent_max_output_tokens=row.agent_max_output_tokens,
        auto_compaction_enabled=row.auto_compaction_enabled,
        parallel_tools_enabled=row.parallel_tools_enabled,
        save_memory_requires_approval=row.save_memory_requires_approval,
        chat_attachment_staged_ttl_hours=row.chat_attachment_staged_ttl_hours,
        chat_attachment_cleanup_interval_seconds=(
            row.chat_attachment_cleanup_interval_seconds
        ),
        max_plot_points=row.max_plot_points,
        max_plot_bytes=row.max_plot_bytes,
        max_plot_nodes=row.max_plot_nodes,
    )


def _apply_config(
    row: AgentConfigModel,
    config: AgentRuntimeConfig,
    *,
    now: datetime,
) -> None:
    row.compaction_threshold_tokens = config.compaction_threshold_tokens
    row.context_window_tokens = config.context_window_tokens
    row.max_parallel_tools = config.max_parallel_tools
    row.max_tool_result_chars = config.max_tool_result_chars
    row.max_page_context_chars = config.max_page_context_chars
    row.max_compaction_summary_chars = config.max_compaction_summary_chars
    row.max_compaction_last_user_chars = config.max_compaction_last_user_chars
    row.model_escalation_enabled = config.model_escalation_enabled
    row.compaction_prompt = config.compaction_prompt
    row.compaction_max_output_tokens = config.compaction_max_output_tokens
    row.agent_max_output_tokens = config.agent_max_output_tokens
    row.auto_compaction_enabled = config.auto_compaction_enabled
    row.parallel_tools_enabled = config.parallel_tools_enabled
    row.save_memory_requires_approval = config.save_memory_requires_approval
    row.chat_attachment_staged_ttl_hours = config.chat_attachment_staged_ttl_hours
    row.chat_attachment_cleanup_interval_seconds = (
        config.chat_attachment_cleanup_interval_seconds
    )
    row.max_plot_points = config.max_plot_points
    row.max_plot_bytes = config.max_plot_bytes
    row.max_plot_nodes = config.max_plot_nodes
    row.updated_at = now


def _values_schema(config: AgentRuntimeConfig) -> AgentSettingsValuesSchema:
    return AgentSettingsValuesSchema(
        compaction_threshold_tokens=config.compaction_threshold_tokens,
        context_window_tokens=config.context_window_tokens,
        max_parallel_tools=config.max_parallel_tools,
        max_tool_result_chars=config.max_tool_result_chars,
        max_page_context_chars=config.max_page_context_chars,
        max_compaction_summary_chars=config.max_compaction_summary_chars,
        max_compaction_last_user_chars=config.max_compaction_last_user_chars,
        model_escalation_enabled=config.model_escalation_enabled,
        compaction_prompt=config.compaction_prompt,
        compaction_max_output_tokens=config.compaction_max_output_tokens,
        agent_max_output_tokens=config.agent_max_output_tokens,
        auto_compaction_enabled=config.auto_compaction_enabled,
        parallel_tools_enabled=config.parallel_tools_enabled,
        save_memory_requires_approval=config.save_memory_requires_approval,
        chat_attachment_staged_ttl_hours=config.chat_attachment_staged_ttl_hours,
        chat_attachment_cleanup_interval_seconds=(
            config.chat_attachment_cleanup_interval_seconds
        ),
        max_plot_points=config.max_plot_points,
        max_plot_bytes=config.max_plot_bytes,
        max_plot_nodes=config.max_plot_nodes,
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
