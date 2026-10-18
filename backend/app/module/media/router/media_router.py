"""HTTP adapters for standalone multimodal media retrieval."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.infrastructure.config.settings import Settings
from app.module.media.dependencies import get_media_service, get_media_settings
from app.module.media.schema.media_schema import MediaSchema, MediaSearchResponseSchema
from app.module.media.service.media_service import MediaService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(prefix="/media", tags=["media"])


@router.post(
    "",
    response_model=MediaSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadMedia",
)
async def upload_media(
    file: Annotated[UploadFile, File()],
    path: Annotated[str | None, Form()] = None,
    caption: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    service: MediaService = Depends(get_media_service),
    settings: Settings = Depends(get_media_settings),
) -> MediaSchema:
    """Upload an image; caption/tags are generated when possible."""
    data = await file.read(settings.max_upload_bytes + 1)
    tag_list = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    return await service.create(
        data=data,
        mime_type=file.content_type,
        path=path,
        caption=caption,
        tags=tag_list,
    )


@router.get(
    "",
    response_model=ListResponseSchema[MediaSchema],
    operation_id="listMedia",
)
async def list_media(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: MediaService = Depends(get_media_service),
) -> ListResponseSchema[MediaSchema]:
    resources = await service.list_media(limit=limit, offset=offset)
    total = await service.count()
    return ListResponseSchema[MediaSchema](
        total_results=total,
        start_index=offset + 1,
        items_per_page=limit,
        resources=resources,
    )


@router.get(
    "/search",
    response_model=MediaSearchResponseSchema,
    operation_id="searchMedia",
)
async def search_media(
    query: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=12, ge=1, le=50),
    service: MediaService = Depends(get_media_service),
) -> MediaSearchResponseSchema:
    """Search image captions and tags (text to image)."""
    return await service.search_text(query=query, limit=limit)


@router.post(
    "/search/image",
    response_model=MediaSearchResponseSchema,
    operation_id="searchMediaByImage",
)
async def search_media_by_image(
    file: Annotated[UploadFile, File()],
    limit: int = Query(default=12, ge=1, le=50),
    service: MediaService = Depends(get_media_service),
    settings: Settings = Depends(get_media_settings),
) -> MediaSearchResponseSchema:
    """Find visually similar images (image to image)."""
    data = await file.read(settings.max_upload_bytes + 1)
    return await service.search_visual(data=data, limit=limit)


@router.get("/{media_id}", response_model=MediaSchema, operation_id="getMedia")
async def get_media(
    media_id: int,
    service: MediaService = Depends(get_media_service),
) -> MediaSchema:
    return await service.get(media_id)


@router.get("/{media_id}/content", operation_id="getMediaContent")
async def get_media_content(
    media_id: int,
    service: MediaService = Depends(get_media_service),
) -> Response:
    data, mime_type, file_name = await service.content(media_id)
    encoded_name = quote(file_name)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@router.post(
    "/{media_id}/describe",
    response_model=MediaSchema,
    operation_id="describeMedia",
)
async def describe_media(
    media_id: int,
    service: MediaService = Depends(get_media_service),
) -> MediaSchema:
    """Regenerate the caption and tags with the configured vision provider."""
    return await service.describe(media_id)


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteMedia",
)
async def delete_media(
    media_id: int,
    service: MediaService = Depends(get_media_service),
) -> Response:
    await service.delete(media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
