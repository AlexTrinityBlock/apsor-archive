"""Deterministic replay from immutable entries to a provider request.

The rules mirror PiAgent's context derivation: a head marker selects the active
range, edits are context-only overrides, tool results are moved directly after
their assistant call in call order, missing results are synthesized, orphan
results are dropped, and failed assistant attempts are excluded from future
requests. A self-headed compaction or reset entry starts a new active range and
therefore a new provider cache prefix without changing the frozen system prompt,
the tools, or any earlier row.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.module.agent.domain.agent_domain import (
    ERROR_FINISH_REASONS,
    KIND_ASSISTANT,
    KIND_SYSTEM,
    KIND_TOOL_RESULT,
    KIND_USER,
    ContextEdit,
    ProviderContext,
    TranscriptEntry,
)
from app.module.agent.domain.tool_catalog import PLOT_TOOL_NAME
from app.module.agent.domain.xml_domain import attributes

# A kept render_plot call replays its figure only up to this encoded size. This
# is a provider-context budget, not a storage limit: a larger figure would cost
# roughly 10k+ tokens on every request of the run and can trigger compaction, so
# the display form alone is replayed instead.
PLOT_CONTEXT_MAX_BYTES = 32_768


def build_context(
    entries: Sequence[TranscriptEntry],
    *,
    cutoff_entry_id: int | None = None,
    keep_plot_run_id: int | None = None,
) -> ProviderContext:
    """Derive the exact provider payload from an ordered entry log."""
    ordered = sorted(
        (entry for entry in entries if cutoff_entry_id is None or entry.id <= cutoff_entry_id),
        key=lambda entry: entry.id,
    )
    if not ordered:
        system_message = {"role": "system", "content": ""}
        return ProviderContext(
            system_message=system_message,
            tools=[],
            messages=[],
            source_entry_ids=[],
            cache_prefix_hash=_prefix_hash(system_message, []),
        )

    active_start = _active_start(ordered)
    active = [entry for entry in ordered if entry.id >= active_start]
    edits = _effective_edits(active)

    system_entries = [entry for entry in active if entry.kind == KIND_SYSTEM]
    if not system_entries:
        earlier = [
            entry for entry in ordered if entry.kind == KIND_SYSTEM and entry.id < active_start
        ]
        if earlier:
            system_entries = [earlier[-1]]

    sections, tools, system_override = _system_snapshot(system_entries, edits)
    system_content = system_override if system_override is not None else _render_sections(sections)
    system_message = {"role": "system", "content": system_content}
    tools_list = list(tools.values())
    prompt_version, tools_version = _system_versions(system_entries)

    contributions, tool_results, source_entry_ids = _contributions(
        active, edits, keep_plot_run_id=keep_plot_run_id
    )
    messages = _assemble_messages(contributions, tool_results)

    return ProviderContext(
        system_message=system_message,
        tools=tools_list,
        messages=messages,
        source_entry_ids=list(dict.fromkeys(source_entry_ids)),
        cache_prefix_hash=_prefix_hash(system_message, tools_list),
        prompt_version=prompt_version,
        tools_version=tools_version,
    )


def active_start_entry_id(entries: Sequence[TranscriptEntry]) -> int | None:
    """Return the id where the newest context boundary starts, if any."""
    if not entries:
        return None
    return _active_start(entries)


def _active_start(entries: Sequence[TranscriptEntry]) -> int:
    markers = [entry for entry in entries if entry.head_entry_id is not None]
    if not markers:
        return entries[0].id
    marker = max(markers, key=lambda entry: entry.id)
    assert marker.head_entry_id is not None
    candidate = marker.head_entry_id
    known_ids = {entry.id for entry in entries}
    if candidate in known_ids:
        return candidate
    return entries[0].id


def _effective_edits(entries: Sequence[TranscriptEntry]) -> dict[int, ContextEdit]:
    edits: dict[int, ContextEdit] = {}
    for entry in entries:
        for edit in entry.edits:
            edits[edit.target_entry_id] = edit
    return edits


def _system_snapshot(
    entries: Sequence[TranscriptEntry],
    edits: Mapping[int, ContextEdit],
) -> tuple[dict[str, tuple[str, str]], dict[str, dict[str, Any]], str | None]:
    sections: dict[str, tuple[str, str]] = {}
    tools: dict[str, dict[str, Any]] = {}
    override: str | None = None

    for entry in entries:
        edit = edits.get(entry.id)
        if edit is not None and edit.action == "omit":
            continue
        if edit is not None and edit.action == "replace":
            replacement = _system_content(edit.messages)
            if replacement is not None:
                override = replacement
            continue

        data = entry.data if isinstance(entry.data, dict) else {}
        raw_sections = data.get("sections")
        has_structured_system = isinstance(raw_sections, list)
        if isinstance(raw_sections, list):
            for raw_section in raw_sections:
                if not isinstance(raw_section, dict):
                    continue
                name = raw_section.get("name")
                title = raw_section.get("title")
                content = raw_section.get("content")
                if not isinstance(name, str) or not name:
                    continue
                if content is None:
                    sections.pop(name, None)
                    continue
                if not isinstance(content, str):
                    continue
                section_title = title if isinstance(title, str) and title else name
                sections[name] = (section_title, content)

        raw_tools = data.get("tools")
        has_tool_delta = isinstance(raw_tools, list) or isinstance(data.get("tools_added"), list)
        if isinstance(raw_tools, list):
            tools = {}
            for raw_tool in raw_tools:
                name = _tool_name(raw_tool)
                if name is not None:
                    tools[name] = deepcopy(raw_tool)

        removed = data.get("tools_removed")
        if isinstance(removed, list):
            for name in removed:
                if isinstance(name, str):
                    tools.pop(name, None)

        added = data.get("tools_added")
        if isinstance(added, list):
            for raw_tool in added:
                name = _tool_name(raw_tool)
                if name is not None:
                    tools[name] = deepcopy(raw_tool)

        if not has_structured_system and not has_tool_delta:
            fallback = _system_content(entry.messages)
            if fallback is not None:
                override = fallback

    return sections, tools, override


def _system_versions(entries: Sequence[TranscriptEntry]) -> tuple[str, str]:
    """Return the prompt/tools versions frozen into the newest system entry."""
    for entry in reversed(entries):
        data = entry.data if isinstance(entry.data, dict) else {}
        prompt_version = data.get("prompt_version")
        tools_version = data.get("tools_version")
        if isinstance(prompt_version, str) and isinstance(tools_version, str):
            return prompt_version, tools_version
    return "", ""


def _contributions(
    entries: Sequence[TranscriptEntry],
    edits: Mapping[int, ContextEdit],
    *,
    keep_plot_run_id: int | None,
) -> tuple[
    list[tuple[TranscriptEntry, list[dict[str, Any]]]],
    dict[str, dict[str, Any]],
    list[int],
]:
    contributions: list[tuple[TranscriptEntry, list[dict[str, Any]]]] = []
    tool_results: dict[str, dict[str, Any]] = {}
    source_entry_ids: list[int] = []
    plot_figures = _plot_figures(entries)

    for entry in entries:
        if entry.kind == KIND_SYSTEM:
            continue
        edit = edits.get(entry.id)
        if edit is not None and edit.action == "omit":
            continue
        if _is_failed_assistant(entry):
            continue

        messages = (
            [deepcopy(message) for message in edit.messages]
            if edit is not None and edit.action == "replace"
            else [deepcopy(message) for message in entry.messages]
        )
        if not messages:
            continue

        if entry.kind == KIND_TOOL_RESULT:
            for message in messages:
                call_id = message.get("tool_call_id")
                if message.get("role") == "tool" and isinstance(call_id, str):
                    tool_results.setdefault(call_id, message)
            source_entry_ids.append(entry.id)
            continue

        normal: list[dict[str, Any]] = []
        for message in messages:
            if message.get("role") == "system":
                continue
            _drop_historical_plot_calls(
                message,
                entry_run_id=entry.by_run_id,
                keep_plot_run_id=keep_plot_run_id,
            )
            _restore_plot_figure(message, plot_figures)
            if _is_empty_assistant(message):
                continue
            normal.append(message)
        if normal:
            if entry.kind == KIND_USER and isinstance(entry.data, dict):
                time_context = entry.data.get("time_context")
                if isinstance(time_context, str) and time_context:
                    for message in normal:
                        content = message.get("content")
                        if message.get("role") == "user" and isinstance(content, str):
                            message["content"] = f"{content}\n\n{time_context}"
            contributions.append((entry, normal))
            source_entry_ids.append(entry.id)

    return contributions, tool_results, source_entry_ids


def _drop_historical_plot_calls(
    message: dict[str, Any],
    *,
    entry_run_id: int | None,
    keep_plot_run_id: int | None,
) -> None:
    """Remove render_plot calls that belong to an earlier agent run.

    A rendered figure is UI state, not reasoning state. Once a run is over, its
    plot calls would replay the whole figure into every later provider request,
    so the provider projection drops them silently. The call's orphaned result
    is dropped by ``_assemble_messages``. A message with no calls left keeps its
    text; a message with neither text nor calls is removed entirely.
    """
    if message.get("role") != "assistant":
        return
    if entry_run_id == keep_plot_run_id:
        return
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return
    kept = [
        call
        for call in raw_calls
        if not (isinstance(call, dict) and _call_name(call) == PLOT_TOOL_NAME)
    ]
    if len(kept) == len(raw_calls):
        return
    if kept:
        message["tool_calls"] = kept
    else:
        message.pop("tool_calls", None)


def _plot_figures(entries: Sequence[TranscriptEntry]) -> dict[str, dict[str, Any]]:
    """Map each successful render_plot call id to its stored figure.

    The tool result is the only place a figure is persisted. Historical calls
    are removed before this map is used, so only the active run can replay one.
    """
    figures: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.kind != KIND_TOOL_RESULT:
            continue
        data = entry.data if isinstance(entry.data, dict) else {}
        if data.get("status") != "ok":
            continue
        plot = data.get("plot")
        if not isinstance(plot, dict):
            continue
        figure = plot.get("figure")
        if not isinstance(figure, dict):
            continue
        for message in entry.messages:
            call_id = message.get("tool_call_id")
            if message.get("role") == "tool" and isinstance(call_id, str):
                figures.setdefault(call_id, figure)
    return figures


def _restore_plot_figure(
    message: dict[str, Any],
    figures: Mapping[str, dict[str, Any]],
) -> None:
    """Normalize a kept render_plot call and rehydrate its stored figure.

    The persisted assistant call holds only title and caption, so the provider
    would otherwise see no figure for the run that rendered it. Rows written
    before that rule are normalized here as well. Oversized or missing figures
    stay display-only; no placeholder is invented.
    """
    if message.get("role") != "assistant":
        return
    for call in _tool_calls(message):
        if _call_name(call) != PLOT_TOOL_NAME:
            continue
        call_id = call.get("id")
        if not isinstance(call_id, str):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        arguments = _parsed_arguments(function.get("arguments"))
        if arguments is None:
            continue
        display: dict[str, Any] = {
            "title": arguments.get("title"),
            "caption": arguments.get("caption"),
        }
        figure = figures.get(call_id)
        if figure is not None:
            size = _encoded_size(figure)
            if size is not None and size <= PLOT_CONTEXT_MAX_BYTES:
                display["figure"] = figure
        function["arguments"] = json.dumps(
            display,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _encoded_size(figure: Mapping[str, Any]) -> int | None:
    """Return the UTF-8 size of the figure's canonical JSON, or None."""
    try:
        encoded = json.dumps(
            figure, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return len(encoded)


def _parsed_arguments(raw: object) -> dict[str, Any] | None:
    """Return tool-call arguments as an object, or None when unparseable."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_empty_assistant(message: Mapping[str, Any]) -> bool:
    """Return whether a message has no text and no tool calls left."""
    if message.get("role") != "assistant":
        return False
    if _tool_calls(message):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return not content.strip()
    return content is None


def _assemble_messages(
    contributions: Sequence[tuple[TranscriptEntry, list[dict[str, Any]]]],
    tool_results: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for _entry, entry_messages in contributions:
        for message in entry_messages:
            if message.get("role") == "tool":
                # Tool messages are emitted next to their call below. Anything
                # left here is an orphan and is deliberately dropped.
                continue
            messages.append(message)
            if message.get("role") != "assistant":
                continue
            for call in _tool_calls(message):
                call_id = call.get("id")
                if not isinstance(call_id, str) or call_id in emitted:
                    continue
                emitted.add(call_id)
                result = tool_results.get(call_id)
                if result is not None:
                    messages.append(deepcopy(result))
                    continue
                messages.append(_synthetic_result(call_id, _call_name(call)))

    # A result whose call was omitted from the active context is an orphan. The
    # loop above never emitted it because no assistant declared that call.
    return messages


def render_tool_result(call_id: str, name: str, content: str) -> str:
    """Wrap provider-facing tool content in the standard XML envelope."""
    return f"<tool_result{attributes({'name': name, 'call_id': call_id})}>{content}</tool_result>"


def _synthetic_result(call_id: str, name: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": render_tool_result(
            call_id,
            name,
            '<error code="tool_result_missing">The tool did not return a result.</error>',
        ),
    }


def _tool_calls(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = message.get("tool_calls")
    if not isinstance(raw, list):
        return []
    return [call for call in raw if isinstance(call, dict)]


def _call_name(call: Mapping[str, Any]) -> str:
    function = call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str) and name:
            return name
    return "unknown"


def _tool_name(tool: object) -> str | None:
    if not isinstance(tool, dict):
        return None
    function = tool.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    return name if isinstance(name, str) and name else None


def _system_content(messages: Sequence[Mapping[str, Any]]) -> str | None:
    parts = [
        str(message.get("content"))
        for message in messages
        if message.get("role") == "system" and isinstance(message.get("content"), str)
    ]
    if not parts:
        return None
    return "\n\n".join(parts)


def _is_failed_assistant(entry: TranscriptEntry) -> bool:
    if entry.kind != KIND_ASSISTANT:
        return False
    data = entry.data if isinstance(entry.data, dict) else {}
    finish_reason = data.get("finish_reason")
    if isinstance(finish_reason, str) and finish_reason.lower() in ERROR_FINISH_REASONS:
        return True
    if data.get("error"):
        return True
    for message in entry.messages:
        reason = message.get("finish_reason")
        if isinstance(reason, str) and reason.lower() in ERROR_FINISH_REASONS:
            return True
    return False


def _render_sections(sections: Mapping[str, tuple[str, str]]) -> str:
    parts: list[str] = []
    for title, content in sections.values():
        heading = f"# {title}".strip()
        body = content.strip()
        parts.append(f"{heading}\n{body}" if body else heading)
    return "\n\n".join(parts)


def prefix_hash(system_message: Mapping[str, Any], tools: Sequence[Mapping[str, Any]]) -> str:
    """Hash the provider-visible prefix: the system message and offered tools."""
    return _prefix_hash(system_message, tools)


def _prefix_hash(system_message: Mapping[str, Any], tools: Sequence[Mapping[str, Any]]) -> str:
    payload = {"system": system_message, "tools": list(tools)}
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["active_start_entry_id", "build_context", "prefix_hash", "render_tool_result"]
