"""Consumer-owned persistence contract for the singleton agent config."""

from typing import Protocol

from app.module.agent.model.agent_config_model import AgentConfigModel


class AgentConfigRepositoryProtocol(Protocol):
    """Read and persist the one row that owns the runtime limits."""

    async def get_singleton(self) -> AgentConfigModel | None: ...

    async def save(self, config: AgentConfigModel) -> AgentConfigModel: ...
