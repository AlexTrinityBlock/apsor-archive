"""HTTP adapter for the frozen tool catalog."""

from fastapi import APIRouter, Depends

from app.dependency.auth import require_authenticated
from app.module.agent.dependencies import get_agent_service
from app.module.agent.schema.agent_schema import AgentToolCatalogSchema
from app.module.agent.service.agent_service import AgentService

router = APIRouter(
    prefix="/tools",
    tags=["agent"],
    dependencies=[Depends(require_authenticated)],
)


@router.get(
    "",
    response_model=AgentToolCatalogSchema,
    operation_id="listAgentTools",
)
async def list_tools(
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentToolCatalogSchema:
    """Return the tool definitions and versions frozen into new conversations."""
    return agent_service.tools_catalog()
