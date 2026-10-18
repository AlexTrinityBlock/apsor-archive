"""HTTP adapters for files, chunk reads, and downloads."""

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.infrastructure.config.settings import Settings
from app.module.knowledge.dependencies import (
    get_app_settings,
    get_file_service,
)
from app.module.knowledge.schema.file_schema import (
    FileChunksSchema,
    FileSchema,
    FileTextCreateSchema,
)
from app.module.knowledge.service.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "",
    response_model=FileSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadFile",
)
async def upload_file(
    path: Annotated[str, Form(min_length=1, max_length=1024)],
    file: Annotated[UploadFile, File()],
    occurred_at: Annotated[datetime | None, Form()] = None,
    file_service: FileService = Depends(get_file_service),
    settings: Settings = Depends(get_app_settings),
) -> FileSchema:
    """Upload one file; the server extracts text and indexes it."""
    data = await file.read(settings.max_upload_bytes + 1)
    return await file_service.ingest_upload(
        path=path,
        data=data,
        content_type=file.content_type,
        occurred_at=occurred_at,
    )


@router.post(
    "/text",
    response_model=FileSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createTextFile",
)
async def create_text_file(
    payload: FileTextCreateSchema,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    """Create a text file directly; useful for the UI editor and automation."""
    return await file_service.ingest_text(
        path=payload.path,
        content=payload.content,
        occurred_at=payload.occurred_at,
    )


@router.get("/{file_id}", response_model=FileSchema, operation_id="getFile")
async def get_file(
    file_id: int,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    return await file_service.get_file(file_id)


@router.get(
    "/{file_id}/chunks/{chunk}",
    response_model=FileChunksSchema,
    operation_id="readFile",
)
async def read_file(
    file_id: int,
    chunk: int,
    chunk_range: int = Query(default=1, ge=0, le=5),
    file_service: FileService = Depends(get_file_service),
) -> FileChunksSchema:
    """Read one chunk and its neighbors (the read_file tool)."""
    return await file_service.read_chunks(
        file_id,
        chunk=chunk,
        chunk_range=chunk_range,
    )


@router.get("/{file_id}/download", operation_id="downloadFile")
async def download_file(
    file_id: int,
    file_service: FileService = Depends(get_file_service),
) -> Response:
    data, file_name, mime_type = await file_service.download(file_id)
    encoded_name = quote(file_name)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        },
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteFile")
async def delete_file(
    file_id: int,
    file_service: FileService = Depends(get_file_service),
) -> Response:
    """Soft-delete a leaf file and hide its branch and chunks."""
    await file_service.delete_file(file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

