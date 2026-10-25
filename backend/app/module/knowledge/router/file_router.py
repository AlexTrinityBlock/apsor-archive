"""HTTP adapters for files, chunk reads, inline content, and downloads."""

import re
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)

from app.infrastructure.config.settings import Settings
from app.module.knowledge.dependencies import (
    get_app_settings,
    get_file_service,
    get_ingest_job_service,
)
from app.module.knowledge.schema.file_schema import (
    FileChunksSchema,
    FileCopySchema,
    FileMoveSchema,
    FileRenameSchema,
    FileSchema,
    FileTextCreateSchema,
    FileTextUpdateSchema,
    IngestJobListSchema,
    IngestJobSchema,
)
from app.module.knowledge.service.file_service import FileOriginal, FileService
from app.module.knowledge.service.ingest_job_service import IngestJobService

router = APIRouter(prefix="/files", tags=["files"])

_BYTE_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)


def _content_disposition(disposition: str, file_name: str) -> str:
    """Build a header-safe inline or attachment disposition for a file name."""
    encoded = quote(file_name, safe="")
    fallback = "".join(
        character if 0x20 <= ord(character) <= 0x7E and character not in {'"', "\\"} else "_"
        for character in file_name
    )
    return f"{disposition}; filename=\"{fallback or 'file'}\"; filename*=UTF-8''{encoded}"


# Inline originals can contain active markup. Everything except PDF gets a
# sandboxed CSP; PDF is left without `sandbox` so the browser's own PDF viewer
# can still open it, while the in-app viewer fetches bytes through PDF.js.
def _content_security_policy(mime_type: str) -> str:
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if normalized == "application/pdf":
        return "default-src 'none'; frame-ancestors 'self'"
    return "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"


def _http_date(value: datetime) -> str:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return format_datetime(moment.astimezone(UTC), usegmt=True)


def _cache_headers(original: FileOriginal) -> dict[str, str]:
    return {
        "Content-Disposition": _content_disposition("inline", original.file_name),
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Security-Policy": _content_security_policy(original.mime_type),
        "Cache-Control": "private, max-age=0, must-revalidate",
        "ETag": f'W/"{original.content_hash}"',
        "Last-Modified": _http_date(original.updated_at),
    }


def _etag_matches(if_none_match: str, content_hash: str) -> bool:
    tag = f'"{content_hash}"'
    return any(
        candidate.strip() in {tag, f"W/{tag}", "*"} for candidate in if_none_match.split(",")
    )


def _byte_range(range_header: str, size: int) -> tuple[int, int] | None:
    """Resolve one RFC 7233 byte range; ``None`` means the range was invalid."""
    match = _BYTE_RANGE.fullmatch(range_header.strip())
    if match is None:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if size == 0:
        return None
    if not first:
        suffix = int(last)
        if suffix <= 0:
            return None
        start = max(0, size - suffix)
        return start, size - 1
    start = int(first)
    if start >= size:
        return None
    if not last:
        return start, size - 1
    end = min(int(last), size - 1)
    if end < start:
        return None
    return start, end


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


@router.post(
    "/async",
    response_model=IngestJobSchema,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadFileAsync",
)
async def upload_file_async(
    path: Annotated[str, Form(min_length=1, max_length=1024)],
    file: Annotated[UploadFile, File()],
    occurred_at: Annotated[datetime | None, Form()] = None,
    ingest_job_service: IngestJobService = Depends(get_ingest_job_service),
    settings: Settings = Depends(get_app_settings),
) -> IngestJobSchema:
    """Store one upload and return immediately with a durable job.

    The synchronous ``POST /files`` endpoint remains available for clients that
    need the fully indexed file in the same response.
    """
    data = await file.read(settings.max_upload_bytes + 1)
    return await ingest_job_service.enqueue_upload(
        path=path,
        data=data,
        content_type=file.content_type,
        occurred_at=occurred_at,
    )


@router.post(
    "/text/async",
    response_model=IngestJobSchema,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createTextFileAsync",
)
async def create_text_file_async(
    payload: FileTextCreateSchema,
    ingest_job_service: IngestJobService = Depends(get_ingest_job_service),
) -> IngestJobSchema:
    """Queue direct text without waiting for chunking and embedding."""
    return await ingest_job_service.enqueue_text(
        path=payload.path,
        content=payload.content,
        occurred_at=payload.occurred_at,
    )


@router.get(
    "/ingest-jobs",
    response_model=IngestJobListSchema,
    operation_id="listIngestJobs",
)
async def list_ingest_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ingest_job_service: IngestJobService = Depends(get_ingest_job_service),
) -> IngestJobListSchema:
    """List active and recent ingestion jobs, newest first."""
    return await ingest_job_service.list_jobs(limit=limit, offset=offset)


@router.get(
    "/ingest-jobs/{job_id}",
    response_model=IngestJobSchema,
    operation_id="getIngestJob",
)
async def get_ingest_job(
    job_id: int,
    ingest_job_service: IngestJobService = Depends(get_ingest_job_service),
) -> IngestJobSchema:
    """Return one job's status and chunking/embedding progress."""
    return await ingest_job_service.get_job(job_id)


@router.post(
    "/ingest-jobs/{job_id}/retry",
    response_model=IngestJobSchema,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryIngestJob",
)
async def retry_ingest_job(
    job_id: int,
    ingest_job_service: IngestJobService = Depends(get_ingest_job_service),
) -> IngestJobSchema:
    """Return a failed job to the queue when its attempt budget allows."""
    return await ingest_job_service.retry_job(job_id)


@router.post(
    "/{file_id}/move",
    response_model=FileSchema,
    status_code=status.HTTP_200_OK,
    operation_id="moveFile",
)
async def move_file(
    file_id: int,
    payload: FileMoveSchema,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    """Move a current file to another logical path without re-indexing."""
    return await file_service.move_file(file_id, path=payload.path)


@router.post(
    "/{file_id}/copy",
    response_model=FileSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="copyFile",
)
async def copy_file(
    file_id: int,
    payload: FileCopySchema,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    """Copy a current file into a new record and index fresh chunks."""
    return await file_service.copy_file(file_id, path=payload.path)


@router.post(
    "/{file_id}/rename",
    response_model=FileSchema,
    status_code=status.HTTP_200_OK,
    operation_id="renameFile",
)
async def rename_file(
    file_id: int,
    payload: FileRenameSchema,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    """Rename a current file without changing its parent folder."""
    return await file_service.rename_file(file_id, file_name_value=payload.file_name)


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
    chunk_range: int = Query(default=1, ge=0, le=25),
    file_service: FileService = Depends(get_file_service),
) -> FileChunksSchema:
    """Read one chunk and its neighbors (the read_file tool)."""
    return await file_service.read_chunks(
        file_id,
        chunk=chunk,
        chunk_range=chunk_range,
    )


@router.get("/{file_id}/content", operation_id="getFileContent")
async def get_file_content(
    file_id: int,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    file_service: FileService = Depends(get_file_service),
) -> Response:
    """Serve the stored original inline, with byte-range support for viewers."""
    original = await file_service.read_original(file_id)
    headers = _cache_headers(original)
    size = len(original.data)

    if if_none_match and _etag_matches(if_none_match, original.content_hash):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    if range_header is None:
        return Response(
            content=original.data,
            media_type=original.mime_type,
            headers=headers,
        )

    resolved = _byte_range(range_header, size)
    if resolved is None:
        headers["Content-Range"] = f"bytes */{size}"
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers=headers,
        )

    start, end = resolved
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(
        content=original.data[start : end + 1],
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=original.mime_type,
        headers=headers,
    )


@router.put(
    "/{file_id}/content",
    response_model=FileSchema,
    status_code=status.HTTP_200_OK,
    operation_id="updateFileContent",
)
async def update_file_content(
    file_id: int,
    payload: FileTextUpdateSchema,
    file_service: FileService = Depends(get_file_service),
) -> FileSchema:
    """更新既有 Markdown 檔案內容，建立新版本並重建索引。"""
    return await file_service.update_markdown_content(
        file_id,
        content=payload.content,
        expected_version=payload.expected_version,
    )


@router.get("/{file_id}/download", operation_id="downloadFile")
async def download_file(
    file_id: int,
    file_service: FileService = Depends(get_file_service),
) -> Response:
    data, file_name, mime_type = await file_service.download(file_id)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Disposition": _content_disposition("attachment", file_name),
            "X-Content-Type-Options": "nosniff",
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
