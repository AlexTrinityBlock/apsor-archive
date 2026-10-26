"""HTTP adapters for durable human approvals of agent writes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.dependency.auth import require_authenticated
from app.module.agent.dependencies import get_agent_service
from app.module.agent.router.conversation_router import (
    _TURN_RESPONSES,
    SSE_HEADERS,
    _sse,
    _wants_json,
)
from app.module.agent.schema.agent_schema import AgentTurnResultSchema
from app.module.agent.service.agent_service import AgentService

router = APIRouter(
    prefix="/approvals",
    tags=["agent"],
    dependencies=[Depends(require_authenticated)],
)


@router.post(
    "/{approval_id}/approve",
    response_model=AgentTurnResultSchema,
    responses=_TURN_RESPONSES,
    operation_id="approveAgentApproval",
)
async def approve_approval(
    approval_id: int,
    accept: Annotated[str | None, Header(alias="Accept")] = None,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Execute the approved write once and resume the waiting run."""
    approval_turn = await agent_service.resolve_approval(
        approval_id,
        approved=True,
    )
    if _wants_json(accept):
        result = await agent_service.collect_approval(approval_turn)
        return JSONResponse(content=result.model_dump(mode="json"))
    return StreamingResponse(
        _sse(agent_service.stream_approval(approval_turn)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post(
    "/{approval_id}/reject",
    response_model=AgentTurnResultSchema,
    responses=_TURN_RESPONSES,
    operation_id="rejectAgentApproval",
)
async def reject_approval(
    approval_id: int,
    accept: Annotated[str | None, Header(alias="Accept")] = None,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Append a rejection result and resume without writing memory."""
    approval_turn = await agent_service.resolve_approval(
        approval_id,
        approved=False,
    )
    if _wants_json(accept):
        result = await agent_service.collect_approval(approval_turn)
        return JSONResponse(content=result.model_dump(mode="json"))
    return StreamingResponse(
        _sse(agent_service.stream_approval(approval_turn)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
