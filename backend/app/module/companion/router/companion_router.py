"""HTTP adapters for custom companions and the companion preference.

Every route is owner-scoped. The preference routes are registered before the
``/{companion_id}`` routes so the literal ``preference`` segment never reaches
the integer path parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.module.companion.dependencies import get_companion_service
from app.module.companion.domain.companion_domain import (
    MAX_FILES_PER_UPLOAD,
    MAX_FRAME_UPLOAD_BYTES,
)
from app.module.companion.exception.domain_error import (
    CompanionFrameLimitError,
    CompanionFrameTooLargeError,
)
from app.module.companion.schema.companion_schema import (
    CompanionCreateSchema,
    CompanionFrameOrderSchema,
    CompanionPreferenceSchema,
    CompanionPreferenceUpdateSchema,
    CompanionSchema,
    CompanionUpdateSchema,
)
from app.module.companion.service.companion_service import CompanionService, FrameUpload
from app.shared.companion_action import CompanionAction
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(prefix="/companions", tags=["companions"])

_IMMUTABLE_CACHE = "private, max-age=31536000, immutable"
_REVALIDATE_CACHE = "private, no-cache"
_IMAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Cookie",
}

Service = Annotated[CompanionService, Depends(get_companion_service)]


@router.get(
    "/preference",
    response_model=CompanionPreferenceSchema,
    operation_id="getCompanionPreference",
)
async def get_companion_preference(service: Service) -> CompanionPreferenceSchema:
    """Return the account's companion choice, visibility, motion, and position."""
    return await service.get_preference()


@router.patch(
    "/preference",
    response_model=CompanionPreferenceSchema,
    operation_id="updateCompanionPreference",
)
async def update_companion_preference(
    payload: CompanionPreferenceUpdateSchema,
    service: Service,
) -> CompanionPreferenceSchema:
    """Change part of the account's companion preference."""
    return await service.update_preference(payload)


@router.get(
    "",
    response_model=ListResponseSchema[CompanionSchema],
    operation_id="listCompanions",
)
async def list_companions(service: Service) -> ListResponseSchema[CompanionSchema]:
    """List the account's custom companions with their frames."""
    companions = await service.list_companions()
    return ListResponseSchema[CompanionSchema](
        total_results=len(companions),
        start_index=1 if companions else 0,
        items_per_page=len(companions),
        resources=companions,
    )


@router.post(
    "",
    response_model=CompanionSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCompanion",
)
async def create_companion(
    payload: CompanionCreateSchema,
    service: Service,
) -> CompanionSchema:
    """Create an empty custom companion."""
    return await service.create_companion(payload)


@router.patch(
    "/{companion_id}",
    response_model=CompanionSchema,
    operation_id="updateCompanion",
)
async def update_companion(
    companion_id: int,
    payload: CompanionUpdateSchema,
    service: Service,
) -> CompanionSchema:
    """Rename a custom companion or change its gender."""
    return await service.update_companion(companion_id, payload)


@router.delete(
    "/{companion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCompanion",
)
async def delete_companion(companion_id: int, service: Service) -> Response:
    """Delete a custom companion and every frame it owns."""
    await service.delete_companion(companion_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{companion_id}/frames",
    response_model=CompanionSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadCompanionFrames",
)
async def upload_companion_frames(
    companion_id: int,
    action: Annotated[CompanionAction, Form()],
    files: Annotated[list[UploadFile], File()],
    service: Service,
) -> CompanionSchema:
    """Append one or more images to an action, in upload order."""
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise CompanionFrameLimitError(MAX_FILES_PER_UPLOAD)
    uploads: list[FrameUpload] = []
    for upload in files:
        data = await upload.read(MAX_FRAME_UPLOAD_BYTES + 1)
        if len(data) > MAX_FRAME_UPLOAD_BYTES:
            raise CompanionFrameTooLargeError(MAX_FRAME_UPLOAD_BYTES)
        uploads.append(FrameUpload(data=data))
    return await service.upload_frames(companion_id, action, uploads)


@router.put(
    "/{companion_id}/frames/order",
    response_model=CompanionSchema,
    operation_id="reorderCompanionFrames",
)
async def reorder_companion_frames(
    companion_id: int,
    payload: CompanionFrameOrderSchema,
    service: Service,
) -> CompanionSchema:
    """Replace the frame order of one action."""
    return await service.reorder_frames(companion_id, payload)


@router.delete(
    "/{companion_id}/frames/{frame_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCompanionFrame",
)
async def delete_companion_frame(
    companion_id: int,
    frame_id: int,
    service: Service,
) -> Response:
    """Delete one frame and close the gap in its action's order."""
    await service.delete_frame(companion_id, frame_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{companion_id}/frames/{frame_id}/image",
    response_class=Response,
    responses={
        200: {
            "description": "The encoded AVIF frame (WebP when AVIF was unavailable).",
            "content": {
                "image/avif": {"schema": {"type": "string", "format": "binary"}},
                "image/webp": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        304: {"description": "The cached frame is still current."},
    },
    operation_id="getCompanionFrame",
)
async def get_companion_frame(
    companion_id: int,
    frame_id: int,
    request: Request,
    service: Service,
    v: Annotated[str | None, Query(max_length=64)] = None,
) -> Response:
    """Return one frame to its owner with a strong ETag.

    Frame bytes never change, so a request whose ``v`` matches the current
    version may be cached for a year; any other request revalidates.
    """
    meta = await service.frame_meta(companion_id, frame_id)
    etag = f'"{meta.etag}"'
    headers = {
        **_IMAGE_HEADERS,
        "ETag": etag,
        "Cache-Control": _IMMUTABLE_CACHE if v == meta.version else _REVALIDATE_CACHE,
    }
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    image = await service.frame_image(companion_id, frame_id)
    return Response(content=image.data, media_type=image.meta.mime_type, headers=headers)


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    candidates = {item.strip().removeprefix("W/") for item in header.split(",")}
    return "*" in candidates or etag in candidates


__all__ = ["router"]
