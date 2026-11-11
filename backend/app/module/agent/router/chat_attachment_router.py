"""HTTP adapters for temporary chat images."""

from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)

from app.dependency.auth import require_stateless_authenticated
from app.infrastructure.config.settings import Settings
from app.module.agent.dependencies import (
    get_app_settings,
    get_chat_attachment_service,
)
from app.module.agent.schema.chat_attachment_schema import (
    CLIENT_KEY_PATTERN,
    AgentChatAttachmentCancelSchema,
    AgentChatAttachmentSchema,
)
from app.module.agent.service.chat_attachment_service import ChatAttachmentService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(
    prefix="/attachments",
    tags=["agent"],
    dependencies=[Depends(require_stateless_authenticated)],
)

_IMAGE_HEADERS = {
    # Temporary screenshots must not survive deletion in a shared browser cache.
    "Cache-Control": "private, no-store",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}


@router.post(
    "",
    response_model=AgentChatAttachmentSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadAgentChatAttachment",
)
async def upload_chat_attachment(
    file: Annotated[UploadFile, File()],
    client_token: Annotated[
        str | None,
        Form(min_length=16, max_length=64, pattern=CLIENT_KEY_PATTERN),
    ] = None,
    service: ChatAttachmentService = Depends(get_chat_attachment_service),
    settings: Settings = Depends(get_app_settings),
) -> AgentChatAttachmentSchema:
    """Store one pasted image in the account's temporary chat area."""
    data = await file.read(settings.chat_attachment_max_bytes + 1)
    return await service.upload(
        data=data,
        file_name=file.filename,
        content_type=file.content_type,
        client_token=client_token,
    )


@router.post(
    "/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="cancelAgentChatAttachment",
)
async def cancel_chat_attachment(
    payload: AgentChatAttachmentCancelSchema,
    service: ChatAttachmentService = Depends(get_chat_attachment_service),
) -> Response:
    """Idempotently discard a staged upload that may still be in flight."""
    await service.cancel_staged(payload.client_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=ListResponseSchema[AgentChatAttachmentSchema],
    operation_id="listAgentChatAttachments",
)
async def list_chat_attachments(
    status_filter: Literal["staged", "attached"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ChatAttachmentService = Depends(get_chat_attachment_service),
) -> ListResponseSchema[AgentChatAttachmentSchema]:
    """Page through temporary images, newest first."""
    resources, total = await service.list_images(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return ListResponseSchema[AgentChatAttachmentSchema](
        total_results=total,
        start_index=offset + 1 if total else 0,
        items_per_page=limit,
        resources=resources,
    )


@router.get(
    "/{attachment_id}/content",
    response_class=Response,
    responses={
        200: {
            "description": "The stored chat image bytes.",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/webp": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
    operation_id="getAgentChatAttachmentContent",
)
async def get_chat_attachment_content(
    attachment_id: int,
    service: ChatAttachmentService = Depends(get_chat_attachment_service),
) -> Response:
    """Return one live image to its owner."""
    content = await service.content(attachment_id)
    return Response(
        content=content.data,
        media_type=content.mime_type,
        headers=_IMAGE_HEADERS,
    )


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAgentChatAttachment",
)
async def delete_chat_attachment(
    attachment_id: int,
    service: ChatAttachmentService = Depends(get_chat_attachment_service),
) -> Response:
    """Delete the stored object and soft-delete its temporary row."""
    await service.delete(attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
