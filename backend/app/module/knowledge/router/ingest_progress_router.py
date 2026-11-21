"""SSE transport for durable ingestion progress.

This router is mounted outside the knowledge aggregate on purpose. The
aggregate carries the request-scoped ``require_authenticated`` guard, which would
keep ``get_db_session`` open for the whole stream. Here the cookie resolves in a
short public session and every subsequent read opens its own owner transaction.
"""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.module.knowledge.dependencies import get_ingest_progress_service
from app.module.knowledge.service.ingest_progress_service import IngestProgressService

router = APIRouter(prefix="/files/ingest-jobs", tags=["files"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}

_STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent ingestion progress (snapshot, progress, keepalive).",
        "content": {
            "text/event-stream": {"schema": {"type": "string"}},
        },
    },
}


@router.get(
    "/{job_id}/events",
    responses=_STREAM_RESPONSES,
    operation_id="streamIngestJobEvents",
)
async def stream_ingest_job_events(
    job_id: int,
    service: IngestProgressService = Depends(get_ingest_progress_service),
) -> StreamingResponse:
    """Stream one owner's durable job progress until it is terminal.

    A missing or cross-account job is a 404 from the snapshot read before the
    response starts. The browser also keeps its one-second polling fallback when
    the stream cannot be established.
    """
    initial = await service.snapshot(job_id)
    return StreamingResponse(
        service.stream(job_id, initial=initial),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


__all__ = ["SSE_HEADERS", "router"]
