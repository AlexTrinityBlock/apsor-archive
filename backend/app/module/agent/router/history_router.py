"""HTTP adapter for one cited past conversation message."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.dependency.auth import require_authenticated
from app.module.agent.dependencies import get_history_message_service
from app.module.agent.schema.agent_schema import AgentHistoryMessageSchema
from app.module.agent.service.history_message_service import AgentHistoryMessageService

router = APIRouter(
    prefix="/history",
    tags=["agent"],
    dependencies=[Depends(require_authenticated)],
)


@router.get(
    "/{entry_id}",
    response_model=AgentHistoryMessageSchema,
    operation_id="getAgentHistoryMessage",
)
async def get_history_message(
    entry_id: Annotated[int, Path(ge=1)],
    history_message_service: AgentHistoryMessageService = Depends(
        get_history_message_service
    ),
) -> AgentHistoryMessageSchema:
    """Return one user/assistant message for a ``[history:id]`` citation.

    Missing, deleted, and another account's entries all use the same 404
    contract, and the endpoint deliberately returns no neighbouring messages.
    """
    read = await history_message_service.read_message(entry_id, message_range=0)
    message = read.target
    return AgentHistoryMessageSchema(
        entry_id=message.entry_id,
        conversation_id=message.conversation_id,
        conversation_title=message.conversation_title,
        role="user" if message.role == "user" else "assistant",
        created_at=message.created_at,
        content=message.content,
    )
