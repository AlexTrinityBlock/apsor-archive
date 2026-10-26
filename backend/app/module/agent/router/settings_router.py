"""HTTP adapters for database-backed agent runtime settings.

The agent configuration is global deployment data. Only the root account may
read or mutate it; normal accounts receive the same configuration indirectly
through the agent runtime.
"""

from fastapi import APIRouter, Depends

from app.dependency.auth import require_root
from app.module.agent.dependencies import get_agent_settings_service
from app.module.agent.schema.settings_schema import (
    AgentSettingsReadSchema,
    AgentSettingsUpdateSchema,
)
from app.module.agent.service.agent_settings_service import AgentSettingsService

router = APIRouter(
    prefix="/settings",
    tags=["agent"],
    dependencies=[Depends(require_root)],
)


@router.get(
    "",
    response_model=AgentSettingsReadSchema,
    operation_id="getAgentSettings",
)
async def get_agent_settings(
    service: AgentSettingsService = Depends(get_agent_settings_service),
) -> AgentSettingsReadSchema:
    """Return the effective runtime limits and the domain defaults."""
    return await service.get_settings()


@router.put(
    "",
    response_model=AgentSettingsReadSchema,
    operation_id="updateAgentSettings",
)
async def update_agent_settings(
    payload: AgentSettingsUpdateSchema,
    service: AgentSettingsService = Depends(get_agent_settings_service),
) -> AgentSettingsReadSchema:
    """Replace every runtime limit with one validated snapshot."""
    return await service.update_settings(payload)


@router.post(
    "/reset",
    response_model=AgentSettingsReadSchema,
    operation_id="resetAgentSettings",
)
async def reset_agent_settings(
    service: AgentSettingsService = Depends(get_agent_settings_service),
) -> AgentSettingsReadSchema:
    """Restore and persist the domain defaults."""
    return await service.reset_settings()
