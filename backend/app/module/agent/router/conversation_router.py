"""HTTP adapters for agent conversations, entries, and turns."""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.module.agent.dependencies import get_agent_service
from app.module.agent.domain.agent_domain import AgentStreamEvent
from app.module.agent.schema.agent_schema import (
    AgentConversationCreateSchema,
    AgentConversationDetailSchema,
    AgentConversationPatchSchema,
    AgentConversationSchema,
    AgentConversationStatus,
    AgentEntryPageSchema,
    AgentMessageCreateSchema,
    AgentRetrySchema,
    AgentTurnResultSchema,
)
from app.module.agent.service.agent_service import AgentService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(prefix="/conversations", tags=["agent"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}

_TURN_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "A server-sent event stream. Send Accept: application/json for JSON."
        ),
        "content": {
            "text/event-stream": {"schema": {"type": "string"}},
        },
    }
}


@router.post(
    "",
    response_model=AgentConversationSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAgentConversation",
)
async def create_conversation(
    payload: AgentConversationCreateSchema,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentConversationSchema:
    """Create a transcript scope and its immutable system entry."""
    return await agent_service.create_conversation(payload)


@router.get(
    "",
    response_model=ListResponseSchema[AgentConversationSchema],
    operation_id="listAgentConversations",
)
async def list_conversations(
    status_filter: AgentConversationStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    agent_service: AgentService = Depends(get_agent_service),
) -> ListResponseSchema[AgentConversationSchema]:
    """List active and archived conversations, newest activity first."""
    resources, total = await agent_service.list_conversations(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return ListResponseSchema[AgentConversationSchema](
        total_results=total,
        start_index=offset + 1,
        items_per_page=limit,
        resources=resources,
    )


@router.get(
    "/{conversation_id}",
    response_model=AgentConversationDetailSchema,
    operation_id="getAgentConversation",
)
async def get_conversation(
    conversation_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentConversationDetailSchema:
    """Return conversation metadata and the first entry page."""
    return await agent_service.get_conversation(conversation_id, limit=limit)


@router.get(
    "/{conversation_id}/entries",
    response_model=AgentEntryPageSchema,
    operation_id="listAgentEntries",
)
async def list_entries(
    conversation_id: int,
    after_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentEntryPageSchema:
    """Read entries in ascending id order after an exclusive cursor."""
    return await agent_service.list_entries(
        conversation_id,
        after_id=after_id,
        limit=limit,
    )


@router.patch(
    "/{conversation_id}",
    response_model=AgentConversationSchema,
    operation_id="updateAgentConversation",
)
async def update_conversation(
    conversation_id: int,
    payload: AgentConversationPatchSchema,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentConversationSchema:
    """Rename or archive a conversation; transcript entries never change."""
    return await agent_service.update_conversation(conversation_id, payload)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAgentConversation",
)
async def delete_conversation(
    conversation_id: int,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Soft-delete a conversation; entries remain for audit."""
    await agent_service.delete_conversation(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=AgentTurnResultSchema,
    responses=_TURN_RESPONSES,
    operation_id="sendAgentMessage",
)
async def send_message(
    conversation_id: int,
    payload: AgentMessageCreateSchema,
    accept: Annotated[str | None, Header(alias="Accept")] = None,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Persist the user entry and run the model/tool loop.

    Browsers receive ``text/event-stream``. Tests and non-streaming clients can
    send ``Accept: application/json`` to receive the completed turn.
    """
    turn = await agent_service.begin_message(conversation_id, payload)
    if _wants_json(accept):
        result = await agent_service.collect_turn(turn)
        return JSONResponse(content=result.model_dump(mode="json"))
    return StreamingResponse(
        _sse(agent_service.stream_turn(turn)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post(
    "/{conversation_id}/retry",
    response_model=AgentTurnResultSchema,
    responses=_TURN_RESPONSES,
    operation_id="retryAgentRun",
)
async def retry_run(
    conversation_id: int,
    payload: AgentRetrySchema,
    accept: Annotated[str | None, Header(alias="Accept")] = None,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Retry the latest failed or cancelled run without duplicating the user entry."""
    turn = await agent_service.begin_retry(conversation_id, payload)
    if _wants_json(accept):
        result = await agent_service.collect_turn(turn)
        return JSONResponse(content=result.model_dump(mode="json"))
    return StreamingResponse(
        _sse(agent_service.stream_turn(turn)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _wants_json(accept: str | None) -> bool:
    if not accept:
        return False
    return "application/json" in accept and "text/event-stream" not in accept


async def _sse(events: AsyncIterator[AgentStreamEvent]) -> AsyncIterator[str]:
    async for event in events:
        payload = json.dumps(
            event.data,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        yield f"event: {event.event}\ndata: {payload}\n\n"
