"""SQLAlchemy persistence for the singleton agent runtime configuration.

The row is global deployment configuration, not private archive content, so it
has no ``user_id``. Normal accounts read it indirectly at runtime; only a
root-guarded request may write it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.model.agent_config_model import AgentConfigModel

SINGLETON_ID = 1


class AgentConfigRepository:
    """One row with ``id=1``; the injected session owns its transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_singleton(self) -> AgentConfigModel | None:
        return await self.session.get(AgentConfigModel, SINGLETON_ID)

    async def save(self, config: AgentConfigModel) -> AgentConfigModel:
        self.session.add(config)
        await self.session.flush()
        return config


__all__ = ["SINGLETON_ID", "AgentConfigRepository"]
