"""Validated tool execution against the knowledge and media services.

Tool failures are values, not HTTP errors: validation problems, missing records,
and service failures become structured ``pi.tool-result`` content so the model can
react and the UI can render a diagnostic card.
"""

import logging
import re
import time
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from app.module.agent.domain.agent_domain import ToolOutcome
from app.module.agent.domain.tool_args import (
    GetMediaArgs,
    PresentResourceArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ReadPathArgs,
    ReadTimelineArgs,
    SaveMemoryArgs,
    SearchKnowledgeArgs,
    SearchMediaArgs,
)
from app.module.agent.domain.tool_catalog import TOOL_SPECS, ToolSpec, tool_catalog
from app.module.agent.domain.xml_domain import attributes, clip, xml_text
from app.module.agent.exception.domain_error import AgentError
from app.module.agent.protocol.tool_service_protocol import (
    AgentToolServices,
    ToolServiceScopeProtocol,
)
from app.module.knowledge.exception.domain_error import (
    FileRecordNotFoundError,
    InvalidChunkWindowError,
    KnowledgeError,
)
from app.module.knowledge.schema.memory_schema import MemorySchema
from app.module.knowledge.schema.timeline_schema import TimelineEventSchema
from app.module.media.exception.domain_error import MediaError

logger = logging.getLogger(__name__)

ERROR_DETAIL_LIMIT = 500
SOURCE_EXCERPT_LIMIT = 1_200
FILE_CHUNK_LIMIT = 4_000
MEMORY_CONTENT_LIMIT = 4_000
MEDIA_TEXT_LIMIT = 2_000
MAX_LISTED_ENTRIES = 100
MAX_TIMELINE_EVENTS = 50
PREVIEW_EXCERPT_LIMIT = 600

_SPECS: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


class AgentToolRegistry:
    """Validate, execute, and normalize one tool call at a time."""

    def __init__(self, service_scope: ToolServiceScopeProtocol) -> None:
        self.service_scope = service_scope

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        """Return the public tool catalog."""
        return tool_catalog()

    @staticmethod
    def requires_confirmation(name: str) -> bool:
        """Return whether a tool must be approved by a human before writing."""
        spec = _SPECS.get(name)
        return bool(spec is not None and spec.requires_confirmation)

    def validate_arguments(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        parse_error: str | None = None,
    ) -> tuple[dict[str, Any] | None, ToolOutcome | None]:
        """Validate a confirmation call and return normalized arguments.

        Invalid arguments produce an ordinary tool error result, not an
        approval. Only validated arguments are persisted on the approval row.
        """
        started = time.perf_counter()
        spec = _SPECS.get(name)
        if spec is None:
            return None, _error(
                name,
                "tool_unavailable",
                f"Tool {name!r} is not available in this conversation.",
                _elapsed_ms(started),
            )
        if parse_error is not None:
            return None, _error(
                name,
                "invalid_tool_arguments",
                parse_error,
                _elapsed_ms(started),
            )
        try:
            parsed = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            return None, _error(
                name,
                "invalid_tool_arguments",
                _format_validation(exc),
                _elapsed_ms(started),
            )
        return parsed.model_dump(mode="json"), None

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        call_id: str,
        max_chars: int,
        parse_error: str | None = None,
        approved: bool = False,
    ) -> ToolOutcome:
        """Execute one tool call and never raise for an expected failure.

        ``approved`` is set only by the backend after a human resolves a durable
        approval. Model-supplied ``user_confirmed`` never authorizes a write.
        """
        started = time.perf_counter()
        spec = _SPECS.get(name)
        if spec is None:
            return _error(
                name,
                "tool_unavailable",
                f"Tool {name!r} is not available in this conversation.",
                _elapsed_ms(started),
            )
        if parse_error is not None:
            return _error(
                name,
                "invalid_tool_arguments",
                parse_error,
                _elapsed_ms(started),
            )
        try:
            parsed = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            return _error(
                name,
                "invalid_tool_arguments",
                _format_validation(exc),
                _elapsed_ms(started),
            )
        if spec.requires_confirmation and not approved:
            return _error(
                name,
                "memory_confirmation_required",
                "The user must approve this memory in the interface before it is saved.",
                _elapsed_ms(started),
            )

        try:
            async with self.service_scope() as services:
                content, data, resource = await _dispatch(name, parsed, services)
        except (KnowledgeError, MediaError, AgentError) as exc:
            return _error(
                name,
                _exception_code(exc),
                str(exc),
                _elapsed_ms(started),
            )
        except Exception:
            logger.exception("Agent tool %s failed", name)
            return _error(
                name,
                "tool_execution_failed",
                "The tool could not complete.",
                _elapsed_ms(started),
            )

        duration = _elapsed_ms(started)
        truncated = len(content) > max_chars
        bounded = clip(content, max_chars)
        payload = {
            **data,
            "tool": name,
            "status": "ok",
            "duration_ms": duration,
            "truncated": truncated,
        }
        return ToolOutcome(content=bounded, data=payload, resource=resource)


async def _dispatch(
    name: str,
    args: BaseModel,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    if name == "search_knowledge" and isinstance(args, SearchKnowledgeArgs):
        return await _search_knowledge(args, services)
    if name == "read_file" and isinstance(args, ReadFileArgs):
        return await _read_file(args, services)
    if name == "read_timeline" and isinstance(args, ReadTimelineArgs):
        return await _read_timeline(args, services)
    if name == "read_path" and isinstance(args, ReadPathArgs):
        return await _read_path(args, services)
    if name == "read_memory" and isinstance(args, ReadMemoryArgs):
        return await _read_memory(args, services)
    if name == "save_memory" and isinstance(args, SaveMemoryArgs):
        return await _save_memory(args, services)
    if name == "search_media" and isinstance(args, SearchMediaArgs):
        return await _search_media(args, services)
    if name == "get_media" and isinstance(args, GetMediaArgs):
        return await _get_media(args, services)
    if name == "present_resource" and isinstance(args, PresentResourceArgs):
        return await _present_resource(args, services)
    raise ValueError(f"No handler is registered for tool {name!r}.")


async def _search_knowledge(
    args: SearchKnowledgeArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.search_service.search(
        args.query,
        result_number=args.result_number,
        include_history=args.include_history,
    )
    content: list[str] = [
        f"<summary>files={len(result.file_results)} "
        f"memories={len(result.memory_results)} "
        f"summaries={len(result.summary_results)}</summary>"
    ]
    for file_result in result.file_results:
        content.append(
            _open(
                "source",
                {
                    "kind": "file",
                    "id": file_result.file_id,
                    "chunk": file_result.chunk,
                    "path": file_result.raw_file_path,
                    "updated": file_result.update_time.isoformat(),
                },
            )
            + xml_text(clip(file_result.content, SOURCE_EXCERPT_LIMIT))
            + _close("source")
        )
    for memory_result in result.memory_results:
        content.append(
            _open(
                "source",
                {
                    "kind": "memory",
                    "id": memory_result.memory_id,
                    "updated": memory_result.update_time.isoformat(),
                },
            )
            + xml_text(clip(memory_result.content, SOURCE_EXCERPT_LIMIT))
            + _close("source")
        )
    for summary_result in result.summary_results:
        content.append(
            _open(
                "source",
                {
                    "kind": "summary",
                    "id": summary_result.memory_summary_id,
                    "start": summary_result.period_start.isoformat(),
                    "end": summary_result.period_end.isoformat(),
                },
            )
            + xml_text(clip(summary_result.content, SOURCE_EXCERPT_LIMIT))
            + _close("source")
        )
    data = {
        "query": result.query,
        "result_number": result.result_number,
        "file_results": [
            {
                "file_id": item.file_id,
                "chunk": item.chunk,
                "raw_file_path": item.raw_file_path,
                "score": item.score,
                "excerpt": _excerpt(item.content),
                "viewer_url": _file_viewer_url(item.file_id, item.chunk),
            }
            for item in result.file_results
        ],
        "memory_results": [
            {
                "memory_id": item.memory_id,
                "score": item.score,
                "excerpt": _excerpt(item.content),
                "viewer_url": _memory_viewer_url(item.memory_id),
            }
            for item in result.memory_results
        ],
        "summary_results": [
            {
                "memory_summary_id": item.memory_summary_id,
                "score": item.score,
                "excerpt": _excerpt(item.content),
            }
            for item in result.summary_results
        ],
    }
    return "".join(content), data, None


async def _read_file(
    args: ReadFileArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.file_service.read_chunks(
        args.file_id,
        chunk=args.chunk,
        chunk_range=args.chunk_range,
    )
    chunks = [
        _open(
            "chunk",
            {
                "index": item.chunk,
                "chars": item.char_count,
                "tokens": item.token_count,
            },
        )
        + xml_text(clip(item.content, FILE_CHUNK_LIMIT))
        + _close("chunk")
        for item in result.chunks
    ]
    content = (
        _open(
            "file",
            {
                "id": result.file_id,
                "path": result.raw_file_path,
                "name": result.file_name,
                "total_chunks": result.total_chunks,
                "chunk_start": result.chunk_start,
                "chunk_end": result.chunk_end,
            },
        )
        + "".join(chunks)
        + _close("file")
    )
    data = {
        "file_id": result.file_id,
        "raw_file_path": result.raw_file_path,
        "file_name": result.file_name,
        "total_chunks": result.total_chunks,
        "chunk_start": result.chunk_start,
        "chunk_end": result.chunk_end,
        "viewer_url": _file_viewer_url(result.file_id, result.chunk_start),
        "chunks": [
            {
                "chunk": item.chunk,
                "char_count": item.char_count,
                "token_count": item.token_count,
                "excerpt": _excerpt(item.content),
            }
            for item in result.chunks
        ],
    }
    return content, data, None


async def _read_timeline(
    args: ReadTimelineArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.timeline_service.get_timeline(
        year=args.year,
        month=args.month,
        day=args.day,
        day_range=args.day_range,
        include_history=args.include_history,
    )
    events = result.events[:MAX_TIMELINE_EVENTS]
    rendered = []
    for event in events:
        event_attributes: dict[str, object] = {
            "kind": event.kind,
            "time": event.time.isoformat(),
        }
        if event.memory_id is not None:
            event_attributes["memory_id"] = event.memory_id
        if event.memory_summary_id is not None:
            event_attributes["summary_id"] = event.memory_summary_id
        if event.file_id is not None:
            event_attributes["file_id"] = event.file_id
        if event.raw_file_path is not None:
            event_attributes["path"] = event.raw_file_path
        rendered.append(
            _open("event", event_attributes)
            + xml_text(clip(event.content, 600))
            + _close("event")
        )
    content = (
        _open(
            "timeline",
            {
                "start": result.range_start.isoformat(),
                "end": result.range_end.isoformat(),
                "total": result.total,
                "sampled": result.sampled,
                "truncated": result.truncated,
            },
        )
        + (
            "".join(rendered)
            if rendered
            else "<summary>No events in this range.</summary>"
        )
        + _close("timeline")
    )
    data = {
        "range_start": result.range_start.isoformat(),
        "range_end": result.range_end.isoformat(),
        "day_range": result.day_range,
        "total": result.total,
        "sampled": result.sampled,
        "events": [
            {
                "kind": event.kind,
                "time": event.time.isoformat(),
                "memory_id": event.memory_id,
                "memory_summary_id": event.memory_summary_id,
                "summary_id": event.memory_summary_id,
                "file_id": event.file_id,
                "content": _excerpt(event.content),
                "viewer_url": _timeline_viewer_url(event),
            }
            for event in events
        ],
    }
    return content, data, None


async def _read_path(
    args: ReadPathArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.file_service.list_path(
        path=args.path,
        path_depth=args.path_depth,
        fuzzy_search=args.fuzzy_search,
    )
    directories = result.directories[:MAX_LISTED_ENTRIES]
    files = result.files[:MAX_LISTED_ENTRIES]
    content = (
        _open("path", {"value": result.path, "fuzzy": result.fuzzy_search})
        + "".join(
            _empty(
                "directory",
                {
                    "path": item.path,
                    "name": item.name,
                    "depth": item.depth,
                },
            )
            for item in directories
        )
        + "".join(
            _empty(
                "file",
                {
                    "id": item.file_id,
                    "path": item.raw_file_path,
                    "name": item.file_name,
                    "chunks": item.total_chunks,
                    "size_bytes": item.size_bytes,
                },
            )
            for item in files
        )
        + _close("path")
    )
    data = {
        "path": result.path,
        "directories": [
            {"path": item.path, "name": item.name, "depth": item.depth}
            for item in directories
        ],
        "files": [
            {
                "file_id": item.file_id,
                "raw_file_path": item.raw_file_path,
                "file_name": item.file_name,
                "total_chunks": item.total_chunks,
                "size_bytes": item.size_bytes,
                "viewer_url": _file_viewer_url(item.file_id),
            }
            for item in files
        ],
    }
    return content, data, None


async def _read_memory(
    args: ReadMemoryArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.memory_service.read_memory(
        args.memory_id,
        memory_range=args.memory_range,
        trace_history=args.trace_history,
    )
    content = _memory_element("memory", result.target)
    content += "".join(
        _memory_element("neighbor", item)
        for item in [*result.neighbors_before, *result.neighbors_after]
    )
    if result.superseded_by is not None:
        content += _memory_element("superseded_by", result.superseded_by)
    content += "".join(_memory_element("supersedes", item) for item in result.supersedes)
    data = {
        "memory_id": result.target.memory_id,
        "status": result.target.status,
        "target": _memory_preview(result.target),
        "neighbors": [
            _memory_preview(item)
            for item in [*result.neighbors_before, *result.neighbors_after]
        ],
        "neighbors_before": [item.memory_id for item in result.neighbors_before],
        "neighbors_after": [item.memory_id for item in result.neighbors_after],
        "supersedes": [item.memory_id for item in result.supersedes],
        "superseded_by": (
            result.superseded_by.memory_id if result.superseded_by is not None else None
        ),
        "chain": [item.memory_id for item in result.chain],
    }
    return content, data, None


async def _save_memory(
    args: SaveMemoryArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.memory_service.save_memory(
        content=args.content,
        supersedes=args.supersedes,
        occurred_at=args.occurred_at,
        source="ai",
        auto_summary=False,
    )
    content = _memory_element("saved", result.memory)
    if result.deprecated:
        content += _empty(
            "deprecated",
            {"ids": ",".join(str(item.memory_id) for item in result.deprecated)},
        )
    data = {
        "memory_id": result.memory.memory_id,
        "status": result.memory.status,
        "memory": _memory_preview(result.memory),
        "supersedes": [item.memory_id for item in result.deprecated],
    }
    return content, data, None


async def _search_media(
    args: SearchMediaArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    result = await services.media_service.search_text(query=args.query, limit=args.limit)
    content: list[str] = [f"<summary>images={len(result.results)}</summary>"]
    for item in result.results:
        excerpt = item.caption or item.summary or item.ocr_text or item.title
        content.append(
            _open(
                "source",
                {
                    "kind": "media",
                    "id": item.media_id,
                    "path": item.raw_file_path,
                    "title": item.title,
                    "mime_type": item.mime_type,
                },
            )
            + xml_text(clip(excerpt, 800))
            + _close("source")
        )
    data = {
        "query": result.query,
        "results": [
            {
                "media_id": item.media_id,
                "raw_file_path": item.raw_file_path,
                "title": item.title,
                "mime_type": item.mime_type,
                "score": item.score,
                "excerpt": _excerpt(
                    item.caption or item.summary or item.ocr_text or item.title
                ),
                "width": item.width,
                "height": item.height,
                "tags": list(item.tags),
                "viewer_url": _media_viewer_url(item.media_id),
            }
            for item in result.results
        ],
    }
    return "".join(content), data, None


async def _get_media(
    args: GetMediaArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    media = await services.media_service.get(args.media_id)
    content = (
        _open(
            "media",
            {
                "id": media.media_id,
                "path": media.raw_file_path,
                "title": media.title,
                "mime_type": media.mime_type,
                "width": media.width,
                "height": media.height,
            },
        )
        + f"<caption>{xml_text(clip(media.caption, MEDIA_TEXT_LIMIT))}</caption>"
        + f"<ocr>{xml_text(clip(media.ocr_text, MEDIA_TEXT_LIMIT))}</ocr>"
        + f"<tags>{xml_text(', '.join(media.tags))}</tags>"
        + _close("media")
    )
    data = {
        "media_id": media.media_id,
        "raw_file_path": media.raw_file_path,
        "file_name": media.file_name,
        "mime_type": media.mime_type,
        "title": media.title,
        "width": media.width,
        "height": media.height,
        "tags": list(media.tags),
        "caption": _excerpt(media.caption),
        "summary": _excerpt(media.summary),
        "ocr_text": _excerpt(media.ocr_text),
        "viewer_url": _media_viewer_url(media.media_id),
    }
    return content, data, None


async def _present_resource(
    args: PresentResourceArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if args.resource_type == "file":
        file = await services.file_service.get_file(args.resource_id)
        if file.deleted_at is not None:
            raise FileRecordNotFoundError(file.id)
        if args.chunk is not None and (
            args.chunk < 1 or args.chunk > file.total_chunks
        ):
            raise InvalidChunkWindowError(
                f"chunk {args.chunk} exceeds the file's {file.total_chunks} chunks."
            )
        viewer_url = f"/viewer/file/{file.id}"
        if args.chunk is not None:
            viewer_url += f"?chunk={args.chunk}"
        resource: dict[str, Any] = {
            "resource_type": "file",
            "resource_id": file.id,
            "viewer_url": viewer_url,
            "title": file.file_name,
            "mime_type": file.mime_type,
            "raw_file_path": file.raw_file_path,
            "chunk": args.chunk,
        }
    elif args.resource_type == "media":
        media = await services.media_service.get(args.resource_id)
        resource = {
            "resource_type": "media",
            "resource_id": media.media_id,
            "viewer_url": f"/viewer/media/{media.media_id}",
            "title": media.title or media.file_name,
            "mime_type": media.mime_type,
            "raw_file_path": media.raw_file_path,
        }
    else:
        result = await services.memory_service.read_memory(
            args.resource_id,
            memory_range=0,
            trace_history=False,
        )
        memory = result.target
        title = " ".join(memory.content.split())[:120]
        resource = {
            "resource_type": "memory",
            "resource_id": memory.memory_id,
            "viewer_url": f"/viewer/memory/{memory.memory_id}",
            "title": title,
            "mime_type": None,
        }

    content = _empty(
        "resource",
        {
            "type": resource["resource_type"],
            "id": resource["resource_id"],
            "url": resource["viewer_url"],
            "title": resource["title"],
            "mime_type": resource["mime_type"],
        },
    )
    return content, {"resource": resource}, resource


def _excerpt(value: str | None, limit: int = PREVIEW_EXCERPT_LIMIT) -> str:
    """Return a whitespace-normalized, bounded UI excerpt."""
    if not value:
        return ""
    return clip(" ".join(value.split()), limit)


def _file_viewer_url(file_id: int, chunk: int | None = None) -> str:
    url = f"/viewer/file/{file_id}"
    if chunk is not None:
        url += f"?chunk={chunk}"
    return url


def _media_viewer_url(media_id: int) -> str:
    return f"/viewer/media/{media_id}"


def _memory_viewer_url(memory_id: int) -> str:
    return f"/viewer/memory/{memory_id}"


def _memory_preview(memory: MemorySchema) -> dict[str, Any]:
    """Return the bounded memory fields used by the inspector."""
    return {
        "memory_id": memory.memory_id,
        "status": memory.status,
        "content": _excerpt(memory.content),
        "update_time": memory.update_time.isoformat(),
    }


def _timeline_viewer_url(event: TimelineEventSchema) -> str | None:
    if event.memory_id is not None:
        return _memory_viewer_url(event.memory_id)
    if event.file_id is not None:
        return _file_viewer_url(event.file_id)
    return None


def _memory_element(name: str, memory: MemorySchema) -> str:
    return (
        _open(
            name,
            {
                "id": memory.memory_id,
                "status": memory.status,
                "time": memory.update_time.isoformat(),
            },
        )
        + xml_text(clip(memory.content, MEMORY_CONTENT_LIMIT))
        + _close(name)
    )


def _error(name: str, code: str, detail: str, duration_ms: int) -> ToolOutcome:
    safe_detail = clip(" ".join(detail.split()), ERROR_DETAIL_LIMIT)
    content = f"<error{attributes({'code': code})}>{xml_text(safe_detail)}</error>"
    return ToolOutcome(
        content=content,
        data={
            "tool": name,
            "status": "error",
            "error_code": code,
            "detail": safe_detail,
            "duration_ms": duration_ms,
        },
        status="error",
        error_code=code,
    )


def _format_validation(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors()[:8]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = str(error.get("msg", "invalid value"))
        messages.append(f"{location}: {message}" if location else message)
    return clip("; ".join(messages) or "Invalid tool arguments.", ERROR_DETAIL_LIMIT)


def _exception_code(exc: Exception) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _open(name: str, values: Mapping[str, object] | None = None) -> str:
    return f"<{name}{attributes(_defined(values))}>"


def _empty(name: str, values: Mapping[str, object] | None = None) -> str:
    return f"<{name}{attributes(_defined(values))}/>"


def _close(name: str) -> str:
    return f"</{name}>"


def _defined(values: Mapping[str, object] | None) -> dict[str, object]:
    return {
        key: value
        for key, value in (values or {}).items()
        if value is not None
    }
