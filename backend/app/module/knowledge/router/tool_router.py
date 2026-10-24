"""LLM-facing tool facade that renders the same services as compact XML.

The JSON API is the application contract. These endpoints exist because an LLM
tool call benefits from a small, explicit payload with stable tags and no
pagination metadata it does not need.
"""

from html import escape as html_escape

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.module.knowledge.dependencies import (
    get_file_service,
    get_memory_service,
    get_search_service,
    get_timeline_service,
)
from app.module.knowledge.schema.memory_schema import MemoryCreateSchema
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.search_service import SearchService
from app.module.knowledge.service.timeline_service import TimelineService

router = APIRouter(prefix="/tools", tags=["tools"])


def _escape(value: str) -> str:
    """Escape XML text without importing the vulnerable SAX parser package."""
    return html_escape(value, quote=False)


def _quoteattr(value: str) -> str:
    """Quote and escape an XML attribute value."""
    return f'"{html_escape(value, quote=True)}"'


def _response(lines: list[str]) -> PlainTextResponse:
    return PlainTextResponse("\n".join(lines))


@router.get("/search_knowledge", operation_id="toolSearchKnowledge")
async def search_knowledge_tool(
    query: str = Query(min_length=1, max_length=200),
    result_number: int = Query(default=2, ge=1, le=20),
    include_history: bool = False,
    search_service: SearchService = Depends(get_search_service),
) -> PlainTextResponse:
    """Return the search_knowledge tool payload as XML."""
    result = await search_service.search(
        query,
        result_number=result_number,
        include_history=include_history,
    )
    lines = [
        (
            f"<search_result query={_quoteattr(result.query)} "
            f'result_number="{result.result_number}" '
            f'text_candidates="{result.stats.text_candidates}" '
            f'vector_candidates="{result.stats.vector_candidates}" '
            f'merged="{result.stats.merged}" '
            f'deduplicated="{result.stats.deduplicated}">'
        )
    ]
    for file_result in result.file_results:
        lines.append(
            f'<file_result file_id="{file_result.file_id}" '
            f"raw_file_path={_quoteattr(file_result.raw_file_path)} "
            f'update_time="{file_result.update_time.isoformat()}" '
            f'chunk="{file_result.chunk}" score="{file_result.score}" '
            f'matched_by="{",".join(file_result.matched_by)}">'
            f"{_escape(file_result.content)}</file_result>"
        )
    for memory_result in result.memory_results:
        lines.append(
            f'<memory_result memory_id="{memory_result.memory_id}" '
            f'update_time="{memory_result.update_time.isoformat()}" '
            f'status="{memory_result.status}" score="{memory_result.score}" '
            f'matched_by="{",".join(memory_result.matched_by)}">'
            f"{_escape(memory_result.content)}</memory_result>"
        )
    for summary_result in result.summary_results:
        lines.append(
            f'<memory_summary_result memory_summary_id="{summary_result.memory_summary_id}" '
            f'update_time="{summary_result.update_time.isoformat()}" '
            f'period_start="{summary_result.period_start.isoformat()}" '
            f'period_end="{summary_result.period_end.isoformat()}" '
            f'score="{summary_result.score}" '
            f'matched_by="{",".join(summary_result.matched_by)}">'
            f"{_escape(summary_result.content)}</memory_summary_result>"
        )
    lines.append("</search_result>")
    return _response(lines)


@router.get("/read_file", operation_id="toolReadFile")
async def read_file_tool(
    file_id: int,
    chunk: int = Query(ge=1),
    chunk_range: int = Query(default=1, ge=0, le=25),
    file_service: FileService = Depends(get_file_service),
) -> PlainTextResponse:
    """Return one chunk window as XML."""
    result = await file_service.read_chunks(
        file_id,
        chunk=chunk,
        chunk_range=chunk_range,
    )
    lines = [
        (
            f'<result file_id="{result.file_id}" '
            f"raw_file_path={_quoteattr(result.raw_file_path)} "
            f'update_time="{result.update_time.isoformat()}" '
            f'total_chunks="{result.total_chunks}" '
            f'chunk_start="{result.chunk_start}" chunk_end="{result.chunk_end}">'
        )
    ]
    for item in result.chunks:
        lines.append(
            f'<chunk index="{item.chunk}" char_count="{item.char_count}">'
            f"{_escape(item.content)}</chunk>"
        )
    lines.append("</result>")
    return _response(lines)


@router.get("/read_timeline", operation_id="toolReadTimeline")
async def read_timeline_tool(
    year: int = Query(ge=1900, le=2200),
    month: int = Query(ge=1, le=12),
    day: int = Query(ge=1, le=31),
    day_range: int = Query(default=1, ge=1, le=366),
    include_history: bool = False,
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> PlainTextResponse:
    """Return a sparse timeline as XML."""
    result = await timeline_service.get_timeline(
        year=year,
        month=month,
        day=day,
        day_range=day_range,
        include_history=include_history,
    )
    range_label = f"{result.range_start.date()} ~ {result.range_end.date()}"
    lines = [
        (
            f"<timeline range={_quoteattr(range_label)} "
            f'sampled="{result.sampled}" total="{result.total}" '
            f'skipped="{result.skipped}" truncated="{str(result.truncated).lower()}">'
        )
    ]
    for item in result.events:
        if item.kind == "memory" and item.memory_id is not None:
            lines.append(
                f'<memory_result memory_id="{item.memory_id}" '
                f'time="{item.time.isoformat()}" anchor="{item.anchor}" '
                f'status="{item.status or "active"}">{_escape(item.content)}</memory_result>'
            )
        elif item.kind == "summary" and item.memory_summary_id is not None:
            lines.append(
                f'<memory_summary_result summary_id="{item.memory_summary_id}" '
                f'time="{item.time.isoformat()}" anchor="{item.anchor}">'
                f"{_escape(item.content)}</memory_summary_result>"
            )
        elif item.kind == "file_update" and item.file_id is not None:
            lines.append(
                f'<file_update file_id="{item.file_id}" '
                f"raw_file_path={_quoteattr(item.raw_file_path or '')} "
                f'time="{item.time.isoformat()}" anchor="{item.anchor}" '
                f'action="{item.action or "updated"}" />'
            )
    for skip in result.skips:
        lines.append(
            f'<skip file_number="{skip.file_number}" '
            f'memory_number="{skip.memory_number}" '
            f'summary_number="{skip.summary_number}" '
            f'from="{skip.from_time.isoformat()}" to="{skip.to_time.isoformat()}" />'
        )
    lines.append("</timeline>")
    return _response(lines)


@router.get("/read_path", operation_id="toolReadPath")
async def read_path_tool(
    path: str = Query(default="/", min_length=1, max_length=1024),
    path_depth: int = Query(default=1, ge=1, le=10),
    fuzzy_search: str | None = Query(default=None, max_length=120),
    file_service: FileService = Depends(get_file_service),
) -> PlainTextResponse:
    """Return a directory listing or fuzzy path matches as XML."""
    result = await file_service.list_path(
        path=path,
        path_depth=path_depth,
        fuzzy_search=fuzzy_search,
    )
    lines = [f"<path_result path={_quoteattr(result.path)}>"]
    for directory in result.directories:
        lines.append(
            f"<dir path={_quoteattr(directory.path)} name={_quoteattr(directory.name)} "
            f'depth="{directory.depth}" />'
        )
    for file in result.files:
        lines.append(
            f'<file file_id="{file.file_id}" '
            f"raw_file_path={_quoteattr(file.raw_file_path)} "
            f'total_chunks="{file.total_chunks}" size_bytes="{file.size_bytes}" '
            f'update_time="{file.update_time.isoformat()}" />'
        )
    lines.append("</path_result>")
    return _response(lines)


@router.post("/save_memory", operation_id="toolSaveMemory")
async def save_memory_tool(
    payload: MemoryCreateSchema,
    memory_service: MemoryService = Depends(get_memory_service),
) -> PlainTextResponse:
    """Create a memory and render the supersession result as XML."""
    result = await memory_service.save_memory(
        content=payload.content,
        supersedes=payload.supersedes,
        occurred_at=payload.occurred_at,
        source=payload.source,
    )
    lines = [
        f'<memory_add memory_id="{result.memory.memory_id}" '
        f'time="{result.memory.update_time.isoformat()}" '
        f'status="{result.memory.status}" />'
    ]
    for memory in result.deprecated:
        lines.append(
            f'<memory id="{memory.memory_id}" status="deprecated" '
            f'superseded_by="{result.memory.memory_id}">'
            f"[deprecated: superseded by {result.memory.memory_id}] "
            f"{_escape(memory.content)}</memory>"
        )
    if result.summary is not None:
        lines.append(
            f'<memory_summary summary_id="{result.summary.memory_summary_id}" '
            f'generator="{result.summary.generator}" '
            f'period_start="{result.summary.period_start.isoformat()}" '
            f'period_end="{result.summary.period_end.isoformat()}">'
            f"{_escape(result.summary.content)}</memory_summary>"
        )
    return _response(lines)


@router.get("/read_memory", operation_id="toolReadMemory")
async def read_memory_tool(
    memory_id: int,
    memory_range: int = Query(default=0, ge=0, le=10),
    trace_history: bool = True,
    memory_service: MemoryService = Depends(get_memory_service),
) -> PlainTextResponse:
    """Render a memory, its neighbours, and its chain as XML."""
    result = await memory_service.read_memory(
        memory_id,
        memory_range=memory_range,
        trace_history=trace_history,
    )
    lines: list[str] = []
    for memory in result.neighbors_before:
        lines.append(
            f'<memory id="{memory.memory_id}" time="{memory.update_time.isoformat()}" '
            f'status="{memory.status}">{_escape(memory.content)}</memory>'
        )
    lines.append(
        f'<memory id="{result.target.memory_id}" target="true" '
        f'time="{result.target.update_time.isoformat()}" status="{result.target.status}" '
        f'superseded_by="{result.target.superseded_by_id or ""}">'
        f"{_escape(result.target.content)}</memory>"
    )
    for memory in result.neighbors_after:
        lines.append(
            f'<memory id="{memory.memory_id}" time="{memory.update_time.isoformat()}" '
            f'status="{memory.status}">{_escape(memory.content)}</memory>'
        )
    for memory in result.chain:
        if memory.memory_id == result.target.memory_id:
            continue
        relation = (
            "superseded_by" if memory.memory_id == result.target.superseded_by_id else "supersedes"
        )
        lines.append(
            f'<memory id="{memory.memory_id}" status="{memory.status}" '
            f'relation="{relation}" time="{memory.update_time.isoformat()}">'
            f"{_escape(memory.content)}</memory>"
        )
    return _response(lines)
