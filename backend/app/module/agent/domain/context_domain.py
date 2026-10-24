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
    ContextEdit,
    ProviderContext,
    TranscriptEntry,
)
from app.module.agent.domain.xml_domain import attributes


def build_context(
    entries: Sequence[TranscriptEntry],
    *,
    cutoff_entry_id: int | None = None,
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

    contributions, tool_results, source_entry_ids = _contributions(active, edits)
    messages = _assemble_messages(contributions, tool_results)

    return ProviderContext(
        system_message=system_message,
        tools=tools_list,
        messages=messages,
        source_entry_ids=list(dict.fromkeys(source_entry_ids)),
        cache_prefix_hash=_prefix_hash(system_message, tools_list),
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


def _contributions(
    entries: Sequence[TranscriptEntry],
    edits: Mapping[int, ContextEdit],
) -> tuple[
    list[tuple[TranscriptEntry, list[dict[str, Any]]]],
    dict[str, dict[str, Any]],
    list[int],
]:
    contributions: list[tuple[TranscriptEntry, list[dict[str, Any]]]] = []
    tool_results: dict[str, dict[str, Any]] = {}
    source_entry_ids: list[int] = []

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
            normal.append(message)
        if normal:
            contributions.append((entry, normal))
            source_entry_ids.append(entry.id)

    return contributions, tool_results, source_entry_ids


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


__all__ = ["active_start_entry_id", "build_context", "render_tool_result"]
