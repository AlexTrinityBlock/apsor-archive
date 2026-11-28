"""Validated tool execution against the knowledge services.

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
from app.module.agent.domain.calculation_domain import evaluate_expression
from app.module.agent.domain.companion_persona_domain import LibrarianMemory
from app.module.agent.domain.history_domain import (
    HISTORY_MESSAGE_MAX_CHARS,
    HistoryMessage,
    HistoryMessageRead,
)
from app.module.agent.domain.plot_spec_domain import (
    DEFAULT_PLOT_LIMITS,
    PlotLimits,
    sanitize_plot_figure,
)
from app.module.agent.domain.tool_args import (
    CalculateArgs,
    CompanionActionArgs,
    HistoryMessageArgs,
    PresentResourceArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ReadPathArgs,
    ReadTimelineArgs,
    RenderPlotArgs,
    SaveMemoryArgs,
    SearchKnowledgeArgs,
    WebFetchArgs,
    WebSearchArgs,
)
from app.module.agent.domain.tool_catalog import (
    TOOL_SPECS,
    ToolSpec,
    tool_catalog,
)
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
from app.module.knowledge.schema.search_schema import SearchResponseSchema
from app.module.knowledge.schema.timeline_schema import TimelineEventSchema
from app.module.web_research.domain.fetch_quality_domain import looks_structurally_incomplete
from app.module.web_research.exception.domain_error import (
    WebFetchNotConfiguredError,
    WebResearchError,
    WebSearchNotConfiguredError,
    WebUrlInvalidError,
    WebUsageLimitExceededError,
)
from app.module.web_research.schema.web_research_schema import WebFetchResponse

logger = logging.getLogger(__name__)

ERROR_DETAIL_LIMIT = 500
SOURCE_EXCERPT_LIMIT = 1_200
FILE_CHUNK_LIMIT = 4_000
MEMORY_CONTENT_LIMIT = 4_000
WEB_FETCH_PREVIEW_LIMIT = 6_000
MAX_LISTED_ENTRIES = 100
MAX_TIMELINE_EVENTS = 50
PREVIEW_EXCERPT_LIMIT = 600
# Per-result content cap. A search result is only a "lead"; when the model really
# needs the full text it should switch to web_fetch. Capping here keeps 10 results
# inside a single tool result.
WEB_RESULT_CONTENT_LIMIT = 2_000
# Fixed provider-only caution appended to every web_search result. It must stay
# free of titles, URLs, counts, or other untrusted content so the bytes are
# deterministic for prompt caching and the hint body cannot break the XML.
WEB_SEARCH_HINT = (
    "These are bounded excerpts, not full documents. Information can continue "
    "past an excerpt, on later pages of the URL, or in matches the provider did "
    "not return; absence from these results is not proof that the source lacks "
    "the detail. If a result matters, call web_fetch with its url, start at "
    "page=1, and follow page, total_pages, has_more, and next_page."
)

WEB_TOOL_NAMES = frozenset({"web_search", "web_fetch"})
COMPRESSED_VIEW = "compressed"

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
        plot_limits: PlotLimits = DEFAULT_PLOT_LIMITS,
    ) -> ToolOutcome:
        """Execute one tool call and never raise for an expected failure.

        ``approved`` is set only by the backend after a human resolves a durable
        approval. Model-supplied ``user_confirmed`` never authorizes a write.
        ``plot_limits`` carries the stored render_plot budgets; its default keeps
        direct callers on the module defaults.
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
                "The user must approve this memory action in the interface before it runs.",
                _elapsed_ms(started),
            )

        try:
            async with self.service_scope() as services:
                content, data, resource = await _dispatch(
                    name,
                    parsed,
                    services,
                    plot_limits,
                )
        except WebResearchError as exc:
            # A failure from the external web provider is a "tool failure", not a
            # stream failure: return a tool result with a stable code so the SSE
            # stream can continue and the model can rewrite the query or explain
            # the limitation.
            return _error(
                name,
                _web_error_code(exc, name),
                str(exc),
                _elapsed_ms(started),
            )
        except (KnowledgeError, AgentError) as exc:
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
        tool_truncated = len(content) > max_chars
        bounded = clip(content, max_chars)
        payload: dict[str, Any] = {
            **data,
            "tool": name,
            "status": "ok",
            "duration_ms": duration,
        }
        if name in WEB_TOOL_NAMES:
            # data["truncated"] for web_search / web_fetch is a service (provider)
            # fact; extra clipping in the tool layer is recorded separately as
            # tool_truncated, and the two must not overwrite each other.
            payload["tool_truncated"] = tool_truncated
            payload.setdefault("truncated", tool_truncated)
        else:
            payload["truncated"] = tool_truncated
        return ToolOutcome(content=bounded, data=payload, resource=resource)


async def _dispatch(
    name: str,
    args: BaseModel,
    services: AgentToolServices,
    plot_limits: PlotLimits,
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
    if name == "history_message" and isinstance(args, HistoryMessageArgs):
        return await _history_message(args, services)
    if name == "save_memory" and isinstance(args, SaveMemoryArgs):
        return await _save_memory(args, services)
    if name == "present_resource" and isinstance(args, PresentResourceArgs):
        return await _present_resource(args, services)
    if name == "calculate" and isinstance(args, CalculateArgs):
        return await _calculate(args)
    if name == "render_plot" and isinstance(args, RenderPlotArgs):
        return await _render_plot(args, plot_limits)
    if name == "web_search" and isinstance(args, WebSearchArgs):
        return await _web_search(args, services)
    if name == "web_fetch" and isinstance(args, WebFetchArgs):
        return await _web_fetch(args, services)
    if name == "companion_action" and isinstance(args, CompanionActionArgs):
        return await _companion_action(args)
    raise ValueError(f"No handler is registered for tool {name!r}.")


LIBRARIAN_MEMORY_GUIDANCE = (
    "These are your own memories, not the Keeper's archive. You may weave one in "
    "as a brief aside if it feels natural; never cite it as evidence."
)


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
        f"summaries={len(result.summary_results)} "
        f"history={len(result.history_results)}</summary>"
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
                    "title": memory_result.title,
                    "updated": memory_result.update_time.isoformat(),
                },
            )
            + xml_text(clip(memory_result.content, SOURCE_EXCERPT_LIMIT))
            + _close("source")
        )
    for history_result in result.history_results:
        content.append(
            _open(
                "history_message",
                {
                    "id": history_result.entry_id,
                    "chunk": history_result.chunk,
                    "score": history_result.score,
                },
            )
            + xml_text(history_result.content)
            + _close("history_message")
        )
    for summary_result in result.summary_results:
        # A summary is a compressed view, not the original text. The XML itself
        # must carry view / memory_count / coverage so the model can tell this is
        # not a raw memory even if it ignores the system prompt.
        coverage_start = summary_result.period_start.isoformat()
        coverage_end = summary_result.period_end.isoformat()
        content.append(
            _open(
                "source",
                {
                    "kind": "summary",
                    "id": summary_result.memory_summary_id,
                    "start": coverage_start,
                    "end": coverage_end,
                    "view": COMPRESSED_VIEW,
                    "memory_count": summary_result.memory_count,
                },
            )
            + _compressed_view(
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                memory_count=summary_result.memory_count,
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
                "title": item.title,
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
                "view": COMPRESSED_VIEW,
                "memory_count": item.memory_count,
                "source_memory_ids": item.source_memory_ids,
                "period_start": item.period_start.isoformat(),
                "period_end": item.period_end.isoformat(),
            }
            for item in result.summary_results
        ],
        "history_results": [
            {
                "entry_id": item.entry_id,
                "chunk": item.chunk,
                "chunk_id": item.chunk_id,
                "score": item.score,
                "vector_score": item.vector_score,
                "text_score": item.text_score,
                "matched_by": item.matched_by,
                "excerpt": _excerpt(item.content),
            }
            for item in result.history_results
        ],
    }
    memories = await _librarian_memories(args.query, result, services)
    if memories:
        # The librarian's own lore is a separate block after every archive
        # source; it never enters the source list or the citation vocabulary.
        content.append(_open("librarian_memories") + xml_text(LIBRARIAN_MEMORY_GUIDANCE))
        for memory in memories:
            content.append(
                _open("librarian_memory", {"id": memory.id, "tier": memory.tier})
                + xml_text(memory.text)
                + _close("librarian_memory")
            )
        content.append(_close("librarian_memories"))
        data["lore"] = [
            {"id": memory.id, "tier": memory.tier, "text": memory.text}
            for memory in memories
        ]
    return "".join(content), data, None


async def _librarian_memories(
    query: str,
    result: SearchResponseSchema,
    services: AgentToolServices,
) -> list[LibrarianMemory]:
    """Return the companion's own memories for this search, never raising."""
    recall = services.librarian_memory
    if recall is None:
        return []
    context = [
        *(item.content for item in result.memory_results[:3]),
        *(item.content for item in result.file_results[:3]),
        *(item.content for item in result.summary_results[:2]),
    ]
    try:
        return await recall.recall(query, [clip(text, 400) for text in context])
    except Exception:
        logger.warning("librarian memory recall failed; continuing without it")
        return []


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
                "content": clip(item.content, FILE_CHUNK_LIMIT),
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
            if event.title:
                event_attributes["title"] = event.title
        if event.memory_summary_id is not None:
            event_attributes["summary_id"] = event.memory_summary_id
        if event.file_id is not None:
            event_attributes["file_id"] = event.file_id
        if event.raw_file_path is not None:
            event_attributes["path"] = event.raw_file_path
        body = xml_text(clip(event.content, 600))
        if event.kind == "summary":
            # A summary event is always marked as a compressed view; memory_count
            # comes from the timeline service via the summary row, and
            # view="compressed" stays even when it is missing so the model never
            # mistakes the text for the original.
            event_attributes["view"] = COMPRESSED_VIEW
            if event.memory_count is not None:
                event_attributes["memory_count"] = event.memory_count
                body = (
                    _compressed_view(
                        coverage_start=(
                            event.period_start.isoformat()
                            if event.period_start is not None
                            else None
                        ),
                        coverage_end=(
                            event.period_end.isoformat() if event.period_end is not None else None
                        ),
                        memory_count=event.memory_count,
                    )
                    + body
                )
            if event.period_start is not None:
                event_attributes["start"] = event.period_start.isoformat()
            if event.period_end is not None:
                event_attributes["end"] = event.period_end.isoformat()
        rendered.append(_open("event", event_attributes) + body + _close("event"))
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
        + ("".join(rendered) if rendered else "<summary>No events in this range.</summary>")
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
                "view": COMPRESSED_VIEW if event.kind == "summary" else None,
                "memory_count": event.memory_count,
                "period_start": (
                    event.period_start.isoformat() if event.period_start is not None else None
                ),
                "period_end": (
                    event.period_end.isoformat() if event.period_end is not None else None
                ),
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
            {"path": item.path, "name": item.name, "depth": item.depth} for item in directories
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
            _memory_preview(item) for item in [*result.neighbors_before, *result.neighbors_after]
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


HISTORY_NEIGHBOR_EXCERPT_LIMIT = 2_000


def _history_element(
    message: HistoryMessage,
    *,
    focus: bool,
    relation: str | None,
    limit: int,
) -> str:
    attributes: dict[str, object] = {
        "id": message.entry_id,
        "role": message.role,
        "conversation_id": message.conversation_id,
        "title": message.conversation_title,
        "time": message.created_at.isoformat(),
    }
    if focus:
        attributes["focus"] = "true"
    if relation is not None:
        attributes["relation"] = relation
    return (
        _open("history_message", attributes)
        + xml_text(clip(message.content, limit))
        + _close("history_message")
    )


async def _history_message(
    args: HistoryMessageArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    """Expand one search hit into the full immutable message and neighbours."""
    result: HistoryMessageRead = await services.history_service.read_message(
        args.message_id,
        message_range=args.message_range,
    )
    target = result.target
    content = _open("history", {"focus_id": target.entry_id}) + _history_element(
        target,
        focus=True,
        relation=None,
        limit=HISTORY_MESSAGE_MAX_CHARS,
    )
    content += "".join(
        _history_element(
            message,
            focus=False,
            relation="before",
            limit=HISTORY_NEIGHBOR_EXCERPT_LIMIT,
        )
        for message in result.before
    )
    content += "".join(
        _history_element(
            message,
            focus=False,
            relation="after",
            limit=HISTORY_NEIGHBOR_EXCERPT_LIMIT,
        )
        for message in result.after
    )
    content += _close("history")
    data = {
        "message_id": target.entry_id,
        "conversation_id": target.conversation_id,
        "conversation_title": target.conversation_title,
        "role": target.role,
        "time": target.created_at.isoformat(),
        "content_truncated": len(target.content) > HISTORY_MESSAGE_MAX_CHARS,
        "content": clip(target.content, HISTORY_MESSAGE_MAX_CHARS),
        "before_ids": [message.entry_id for message in result.before],
        "after_ids": [message.entry_id for message in result.after],
        "neighbors": [
            {
                "entry_id": message.entry_id,
                "role": message.role,
                "time": message.created_at.isoformat(),
                "content": clip(message.content, HISTORY_NEIGHBOR_EXCERPT_LIMIT),
            }
            for message in [*result.before, *result.after]
        ],
    }
    return content, data, None


async def _save_memory(
    args: SaveMemoryArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    if args.content is None or not args.content.strip():
        # Deprecation-only: no replacement row is written. The model sees one
        # element per retired memory so it can confirm the exact ids and titles.
        deprecated = await services.memory_service.deprecate_memories(
            args.supersedes,
            reason=args.reason,
        )
        content = "".join(
            _open(
                "deprecated",
                {
                    "id": item.memory_id,
                    "title": item.title,
                    "status": item.status,
                    "reason": item.deprecated_reason,
                },
            )
            + xml_text(clip(item.content, MEMORY_CONTENT_LIMIT))
            + _close("deprecated")
            for item in deprecated
        )
        data: dict[str, Any] = {
            "mode": "deprecate",
            "memory_ids": [item.memory_id for item in deprecated],
            "deprecated": [_memory_preview(item) for item in deprecated],
            "reason": args.reason,
        }
        return content, data, None

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
        "mode": "save",
        "memory_id": result.memory.memory_id,
        "status": result.memory.status,
        "memory": _memory_preview(result.memory),
        "supersedes": [item.memory_id for item in result.deprecated],
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
        if args.chunk is not None and (args.chunk < 1 or args.chunk > file.total_chunks):
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
            # UI-only: lets the chat card reserve its box and paint the tiny
            # WebP immediately. The model-facing XML never includes it.
            "thumbnail": (
                file.thumbnail.model_dump(mode="json") if file.thumbnail is not None else None
            ),
        }
    elif args.resource_type == "memory":
        result = await services.memory_service.read_memory(
            args.resource_id,
            memory_range=0,
            trace_history=False,
        )
        memory = result.target
        resource = {
            "resource_type": "memory",
            "resource_id": memory.memory_id,
            "viewer_url": f"/viewer/memory/{memory.memory_id}",
            "title": memory.title,
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


async def _calculate(args: CalculateArgs) -> tuple[str, dict[str, Any], None]:
    """Evaluate one expression; the calculator touches no service or database."""
    result = evaluate_expression(args.expression)
    content = _empty(
        "calculation",
        {"expression": result.expression, "result": result.formatted},
    )
    data = {
        "expression": result.expression,
        "result": result.result,
        "formatted": result.formatted,
    }
    return content, data, None


async def _companion_action(
    args: CompanionActionArgs,
) -> tuple[str, dict[str, Any], None]:
    """Acknowledge one companion gesture; it touches no service or database.

    The browser reacts to the ``tool_start``/``tool_end`` events and reads the
    action from the result data, so the tool only echoes the validated choice.
    """
    note = args.note.strip() if args.note else None
    content = _empty(
        "companion_action",
        {"action": args.action, "status": "performed"},
    )
    data: dict[str, Any] = {"ok": True, "action": args.action, "note": note or None}
    return content, data, None


async def _render_plot(
    args: RenderPlotArgs,
    plot_limits: PlotLimits,
) -> tuple[str, dict[str, Any], None]:
    """Sanitize one figure and keep the full plot out of the provider content.

    The provider only sees a short receipt that states the chart is already
    visible. The complete figure travels in ``data.plot.figure``, which the UI
    renders and the provider never reads. ``plot_limits`` comes from the runtime
    snapshot, so the budgets can change without editing code.
    """
    sanitized = sanitize_plot_figure(
        args.figure.model_dump(exclude_none=True),
        max_points=plot_limits.max_points,
        max_bytes=plot_limits.max_bytes,
        max_nodes=plot_limits.max_nodes,
    )
    receipt_values: dict[str, object] = {
        "title": args.title,
        "traces": sanitized.trace_count,
        "points": sanitized.point_count,
    }
    if sanitized.grid_rows is not None and sanitized.grid_columns is not None:
        receipt_values["rows"] = sanitized.grid_rows
        receipt_values["cols"] = sanitized.grid_columns
    receipt_values["visible"] = "true"
    content = (
        _open("plot_rendered", receipt_values)
        + "The chart is already rendered and visible to the user. Do not call "
        "render_plot again for this request. Reply with a one- or two-sentence "
        "explanation of the chart."
    )
    if sanitized.grid_rows is not None and sanitized.grid_columns is not None:
        content += (
            f" This is a complete {sanitized.grid_rows} x "
            f"{sanitized.grid_columns} grid of {sanitized.point_count} cells; "
            "points counts every cell, not one row."
        )
    content += _close("plot_rendered")
    data = {
        "plot": {
            "version": 1,
            "format": "plotly",
            "title": args.title,
            "caption": args.caption,
            "figure": sanitized.figure,
            "stats": {
                "trace_count": sanitized.trace_count,
                "point_count": sanitized.point_count,
                "byte_size": sanitized.byte_size,
            },
        }
    }
    return content, data, None


async def _web_search(
    args: WebSearchArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    """Search the public web and render bounded, citable results.

    The XML shape is fixed: ``<web_search>`` containing ``<result>`` elements and
    one trailing ``<search_hint>``. provider and retrieved_at sit on the root
    element because they are the source facts for the whole batch of results, so
    the model only has to look at the root attributes when citing. ``cached`` /
    ``truncated`` are on the root as well, telling the model that this is a
    cached result or clipped text and keeping it from mistaking cached content
    for a live observation.

    Every result exposes ``content_chars`` / ``excerpt_chars`` /
    ``excerpt_truncated`` so clipping is local and visible instead of only a
    root flag. The unconditional ``<search_hint>`` names the clipping layer and
    the ``web_fetch`` recovery path, because a search result is always an
    excerpt, never the full document.
    """
    result = await services.web_research_service.search(
        args.query,
        max_results=args.max_results,
        search_depth=args.search_depth,
        include_domains=args.include_domains,
        exclude_domains=args.exclude_domains,
        objective=args.objective,
    )
    retrieved_at = result.retrieved_at.isoformat()
    rendered: list[str] = []
    clipped_any = False
    for index, item in enumerate(result.results, start=1):
        excerpt = clip(item.content, WEB_RESULT_CONTENT_LIMIT)
        excerpt_truncated = len(item.content) > WEB_RESULT_CONTENT_LIMIT
        clipped_any = clipped_any or excerpt_truncated
        rendered.append(
            _open(
                "result",
                {
                    "index": index,
                    "title": item.title,
                    "url": item.url,
                    # A provider does not always return a score; None is filtered
                    # out by _defined in _open.
                    "score": round(item.score, 4) if item.score is not None else None,
                    "content_chars": len(item.content),
                    "excerpt_chars": len(excerpt),
                    "excerpt_truncated": _xml_bool(excerpt_truncated),
                },
            )
            + xml_text(excerpt)
            + _close("result")
        )
    provider_truncated = result.truncated
    content = (
        _open(
            "web_search",
            {
                "query": args.query,
                "provider": result.provider,
                "results": len(result.results),
                "retrieved_at": retrieved_at,
                "cached": _xml_bool(result.cached),
                # If any layer clipped, provider or agent, the XML is marked truncated.
                "truncated": _xml_bool(provider_truncated or clipped_any),
            },
        )
        + "".join(rendered)
        + _search_hint(
            provider_truncated=provider_truncated,
            excerpts_clipped=clipped_any,
        )
        + _close("web_search")
    )
    data = {
        "query": args.query,
        "provider": result.provider,
        "results": [
            {
                "title": item.title,
                "url": item.url,
                "excerpt": _excerpt(item.content),
                "score": item.score,
            }
            for item in result.results
        ],
        "retrieved_at": retrieved_at,
        "cached": result.cached,
        "truncated": result.truncated,
        "excerpt_truncated": clipped_any,
    }
    return content, data, None


def _search_hint(*, provider_truncated: bool, excerpts_clipped: bool) -> str:
    """Render the unconditional, fixed-text ``<search_hint>`` child.

    Search results are always bounded excerpts, so the hint is present even when
    nothing was clipped. Only the attributes and one fixed sentence vary; no
    title, URL, or provider text is interpolated, which keeps the output
    deterministic and the XML body safe.
    """
    body = WEB_SEARCH_HINT
    if excerpts_clipped and provider_truncated:
        body += (
            " Both the excerpt limit and the provider's result cap clipped this "
            "reply, so call web_fetch with the source url before concluding the "
            "fact is absent."
        )
    elif excerpts_clipped:
        body += (
            " The excerpt limit clipped at least one result, so call web_fetch "
            "with the source url before concluding the fact is absent."
        )
    elif provider_truncated:
        body += (
            " The provider capped its own result set, so call web_fetch with the "
            "source url before concluding the fact is absent."
        )
    return (
        _open(
            "search_hint",
            {
                "truncated": _xml_bool(provider_truncated or excerpts_clipped),
                "excerpts_clipped": _xml_bool(excerpts_clipped),
                "provider_truncated": _xml_bool(provider_truncated),
                "excerpt_limit": WEB_RESULT_CONTENT_LIMIT,
            },
        )
        + xml_text(body)
        + _close("search_hint")
    )


async def _web_fetch(
    args: WebFetchArgs,
    services: AgentToolServices,
) -> tuple[str, dict[str, Any], None]:
    """Fetch one public URL and return one server-defined Markdown page.

    ``content_chars`` and ``truncated`` are both computed from the service's real
    response, and the XML attributes are only a projection of the same fact; extra
    clipping in the tool layer is recorded separately as ``tool_truncated`` by
    ``execute`` and does not override the provider semantics here. The trailing
    footer tells the model the current page number and how to continue in plain
    text, because the model always reads the tool result even when it ignores the
    system prompt.

    ``page`` is forwarded to the service only when it was sent explicitly;
    otherwise the service decides the starting point from the legacy ``offset`` or
    from the default page 1. ``max_chars`` / ``limit`` are compatibility fields
    frozen for old conversations and are not used in page mode.
    """
    result = await services.web_research_service.fetch(
        args.url,
        page=args.page if "page" in args.model_fields_set else None,
        offset=args.offset,
    )
    retrieved_at = result.retrieved_at.isoformat()
    content_chars = len(result.content)
    content = (
        _open(
            "web_fetch",
            {
                "url": result.url,
                "provider": result.provider,
                "retrieved_at": retrieved_at,
                "content_chars": content_chars,
                "page": result.page,
                "total_pages": result.total_pages,
                "page_chars": result.page_chars,
                "total_chars": result.total_chars,
                "has_more": _xml_bool(result.has_more),
                # None is filtered by _defined so next_page="None" is never emitted.
                "next_page": result.next_page,
                "source_truncated": _xml_bool(result.source_truncated),
                "truncated": _xml_bool(result.truncated),
                "cached": _xml_bool(result.cached),
            },
        )
        + xml_text(result.content)
        + "\n"
        + _web_fetch_footer(result)
        + _close("web_fetch")
    )
    data = {
        "url": result.url,
        "provider": result.provider,
        "content_chars": content_chars,
        "content": clip(result.content, WEB_FETCH_PREVIEW_LIMIT),
        "page": result.page,
        "total_pages": result.total_pages,
        "page_chars": result.page_chars,
        "total_chars": result.total_chars,
        "has_more": result.has_more,
        "next_page": result.next_page,
        "source_truncated": result.source_truncated,
        "truncated": result.truncated,
        "cached": result.cached,
        "retrieved_at": retrieved_at,
    }
    return content, data, None


def _web_fetch_footer(result: WebFetchResponse) -> str:
    """Render the plain-text continuation hint appended inside <web_fetch>.

    Pages are contiguous, so ``next_page`` is always exact when ``has_more`` is
    true. All values are integers from the service, so the footer cannot smuggle
    unescaped user content into XML.
    """
    if result.page < 1 or result.page > result.total_pages:
        footer = (
            f"[web_fetch: page {result.page} is past the end "
            f"({result.total_pages} pages).]"
        )
    elif result.has_more:
        next_page = result.next_page or result.page + 1
        footer = (
            f"[web_fetch: page {result.page}/{result.total_pages}. "
            f"More content: call web_fetch again with page={next_page}.]"
        )
    else:
        footer = (
            f"[web_fetch: page {result.page}/{result.total_pages}. "
            "End of extracted content.]"
        )
        if looks_structurally_incomplete(result.content):
            footer += (
                " A heading has no body before the next heading; the extractor "
                "may have skipped that section. Do not treat it as empty without "
                "another source."
            )
    if result.source_truncated:
        footer += " The source exceeded the fetch cache cap and was truncated."
    return footer


def _compressed_view(
    *,
    coverage_start: str | None,
    coverage_end: str | None,
    memory_count: int,
) -> str:
    """Render the explicit compressed-view marker for a summary.

    Why this goes into the XML instead of only the system prompt: the model may
    ignore the prompt, but it always reads the tool result it is citing.
    ``coverage_start`` / ``coverage_end`` describe the period the summary covers,
    ``source_memory_count`` is the number of original memories, and the fixed body
    tells the model outright to use ``read_memory`` or ``read_timeline`` when exact
    wording matters. The body is deliberately in English, matching the language of
    the other tool results.
    """
    notice = (
        f"This is a compressed summary of {memory_count} original memories, "
        "not the complete original content. Use read_memory for a specific memory "
        "or read_timeline for the covered period when exact wording matters."
    )
    # Do not emit coverage_start="None" when the coverage is unknown; only a period
    # that really exists goes into the XML, so the model never treats the string
    # "None" as a valid date.
    values: dict[str, object] = {"source_memory_count": memory_count}
    if coverage_start is not None:
        values["coverage_start"] = coverage_start
    if coverage_end is not None:
        values["coverage_end"] = coverage_end
    return _open("compressed_view", values) + xml_text(notice) + _close("compressed_view")


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


def _memory_viewer_url(memory_id: int) -> str:
    return f"/viewer/memory/{memory_id}"


def _memory_preview(memory: MemorySchema) -> dict[str, Any]:
    """Return the bounded memory fields used by the inspector."""
    return {
        "memory_id": memory.memory_id,
        "title": memory.title,
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
                "title": memory.title,
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


_WEB_DEFAULT_CODES = {
    "web_search": "web_provider_error",
    "web_fetch": "web_fetch_failed",
}


def _web_error_code(exc: WebResearchError, tool_name: str) -> str:
    """Map a web-research failure to one of the six stable tool error codes.

    Classification always uses ``isinstance`` because ``web_research`` already
    defines the leaf exceptions as a stable domain contract; an unknown leaf falls
    through to that tool's generic code (search -> ``web_provider_error``,
    fetch -> ``web_fetch_failed``), and the model can still use the code to decide
    whether to rewrite the query or explain the limitation.

    Why the generic codes are split per tool: the same provider failure is "the
    query failed" in a search context and "this page could not be fetched" in a
    fetch context, and the two suggest different next actions to the model.
    not-configured deliberately maps to each capability as well, so the user knows
    which slot to configure in Settings.
    """
    if isinstance(exc, WebUrlInvalidError):
        return "web_url_invalid"
    if isinstance(exc, WebSearchNotConfiguredError):
        return "web_search_not_configured"
    if isinstance(exc, WebFetchNotConfiguredError):
        return "web_fetch_not_configured"
    if isinstance(exc, WebUsageLimitExceededError):
        return "web_usage_limit_exceeded"
    return _WEB_DEFAULT_CODES.get(tool_name, "web_provider_error")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _open(name: str, values: Mapping[str, object] | None = None) -> str:
    return f"<{name}{attributes(_defined(values))}>"


def _empty(name: str, values: Mapping[str, object] | None = None) -> str:
    return f"<{name}{attributes(_defined(values))}/>"


def _close(name: str) -> str:
    return f"</{name}>"


def _defined(values: Mapping[str, object] | None) -> dict[str, object]:
    return {key: value for key, value in (values or {}).items() if value is not None}


def _xml_bool(value: bool) -> str:
    """Render a Python bool as the lowercase XML attribute form."""
    return "true" if value else "false"
