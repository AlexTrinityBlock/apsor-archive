"""Deterministic context estimation and compaction summaries.

Compaction never calls a provider. It estimates the active context from the
persisted entries and builds one bounded ``pi.compaction`` message. The entry's
``head_entry_id`` starts a new context segment, so the old prefix is hidden from
future requests without rewriting any immutable row.
"""

import json
import re
from collections.abc import Sequence
from typing import Any

from app.module.agent.domain.agent_domain import (
    ERROR_FINISH_REASONS,
    KIND_ASSISTANT,
    KIND_COMPACTION,
    KIND_PAGE_CONTEXT,
    KIND_RESET,
    KIND_SYSTEM,
    KIND_TOOL_RESULT,
    KIND_USER,
    MAX_COMPACTION_LAST_USER_CHARS,
    MAX_COMPACTION_SUMMARY_CHARS,
    EntryDraft,
    TranscriptEntry,
)
from app.module.agent.domain.context_domain import (
    active_start_entry_id,
    build_context,
)
from app.module.agent.domain.xml_domain import clip, xml_text

MAX_SUMMARY_ITEM_CHARS = 280
MAX_COMPACTION_CARRY_CHARS = 1_200
MAX_SUMMARY_ITEMS = 40
CHARS_PER_ESTIMATED_TOKEN = 3
_CITATION_PATTERN = re.compile(r"\[(?:file|memory|summary):\d+(?:#\d+)?\]")


def active_context_entries(
    entries: Sequence[TranscriptEntry],
) -> list[TranscriptEntry]:
    """Return entries inside the newest head/reset/compaction boundary."""
    ordered = sorted(entries, key=lambda entry: entry.id)
    start = active_start_entry_id(ordered)
    if start is None:
        return []
    return [entry for entry in ordered if entry.id >= start]


def compactable_context_entries(
    entries: Sequence[TranscriptEntry],
) -> list[TranscriptEntry]:
    """Return active entries that carry conversation state, excluding system."""
    return [entry for entry in active_context_entries(entries) if entry.kind != KIND_SYSTEM]


def estimate_context_tokens(entries: Sequence[TranscriptEntry]) -> int:
    """Estimate provider tokens without calling the provider.

    The estimate is intentionally conservative: a serialized character count at
    three characters per token, compared against the latest valid assistant
    usage. The larger value wins so the auto-compaction threshold cannot be
    bypassed by a terse usage report.
    """
    ordered = sorted(entries, key=lambda entry: entry.id)
    if not ordered:
        return 0
    context = build_context(ordered)
    serialized = json.dumps(
        {
            "system": context.system_message,
            "tools": context.tools,
            "messages": context.messages,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    char_estimate = (len(serialized) + CHARS_PER_ESTIMATED_TOKEN - 1) // CHARS_PER_ESTIMATED_TOKEN

    start = active_start_entry_id(ordered)
    usage_estimate = 0
    for entry in ordered:
        if start is not None and entry.id < start:
            continue
        if entry.kind != KIND_ASSISTANT:
            continue
        data = entry.data if isinstance(entry.data, dict) else {}
        if data.get("error"):
            continue
        finish_reason = data.get("finish_reason")
        if isinstance(finish_reason, str) and finish_reason.lower() in ERROR_FINISH_REASONS:
            continue
        usage = data.get("usage")
        if not isinstance(usage, dict):
            continue
        prompt_tokens = _int_value(usage.get("prompt_tokens"))
        completion_tokens = _int_value(usage.get("completion_tokens"))
        if prompt_tokens > 0:
            usage_estimate = prompt_tokens + completion_tokens
    return max(char_estimate, usage_estimate)


def build_compaction_draft(
    entries: Sequence[TranscriptEntry],
    *,
    reason: str,
    auto: bool,
    max_summary_chars: int = MAX_COMPACTION_SUMMARY_CHARS,
    max_last_user_chars: int = MAX_COMPACTION_LAST_USER_CHARS,
) -> EntryDraft:
    """Build the provider message and UI data for one compaction entry.

    The summary and carried last-user-input caps come from the active runtime
    config snapshot; the defaults keep the pure builder usable in isolation.
    """
    compactable = compactable_context_entries(entries)
    selected = compactable[-MAX_SUMMARY_ITEMS:]
    omitted = len(compactable) - len(selected)
    lines: list[str] = []
    if omitted > 0:
        lines.append(f"[{omitted} earlier entries omitted]")
    lines.extend(_summary_line(entry) for entry in selected)
    summary = "\n".join(line for line in lines if line)
    if not summary:
        summary = "No active conversation content to compact."
    summary = clip(summary, max_summary_chars)

    last_user_entry = next(
        (entry for entry in reversed(compactable) if entry.kind == KIND_USER and _user_text(entry)),
        None,
    )
    last_user_text = (
        clip(_one_line(_user_text(last_user_entry)), max_last_user_chars)
        if last_user_entry is not None
        else ""
    )

    values: list[str] = ["<compaction>"]
    if last_user_text:
        values.append(f"<last_user_input>{xml_text(last_user_text)}</last_user_input>")
    values.append(f"<summary>{xml_text(summary)}</summary>")
    values.append("</compaction>")

    return EntryDraft(
        kind=KIND_COMPACTION,
        messages=[{"role": "user", "content": "".join(values)}],
        data={
            "reason": reason,
            "summary_chars": len(summary),
            "last_user_entry_id": (last_user_entry.id if last_user_entry is not None else None),
            "source_entry_ids": [entry.id for entry in selected],
            "auto": auto,
        },
    )


def _summary_line(entry: TranscriptEntry) -> str:
    data = entry.data if isinstance(entry.data, dict) else {}
    if entry.kind == KIND_USER:
        return f"User: {clip(_one_line(_user_text(entry)), MAX_SUMMARY_ITEM_CHARS)}"
    if entry.kind == KIND_ASSISTANT:
        assistant_text = _assistant_text(entry)
        text = clip(
            _one_line(assistant_text),
            MAX_SUMMARY_ITEM_CHARS,
        )
        citations = ",".join(sorted(set(_CITATION_PATTERN.findall(assistant_text))))
        suffix = f" citations={citations}" if citations else ""
        return f"Assistant: {text}{suffix}" if text else "Assistant: (empty)"
    if entry.kind == KIND_TOOL_RESULT:
        name = str(data.get("tool") or "tool")
        status = str(data.get("status") or "unknown")
        error_code = data.get("error_code")
        suffix = f" error={error_code}" if error_code else ""
        return f"Tool {name}: {status}{suffix}"
    if entry.kind == KIND_PAGE_CONTEXT:
        key = data.get("page_key")
        path = data.get("path")
        return f"Page context: {key or path or 'unknown'}"
    if entry.kind == KIND_RESET:
        return f"Boundary: context cleared ({data.get('reason') or 'reset'})."
    if entry.kind == KIND_COMPACTION:
        previous = _role_text(entry, "user")
        if previous:
            return "Previous compaction: " + clip(
                _one_line(previous),
                MAX_COMPACTION_CARRY_CHARS,
            )
        return f"Boundary: context compacted ({data.get('reason') or 'compaction'})."
    return f"Entry {entry.kind}."


def _user_text(entry: TranscriptEntry | None) -> str:
    if entry is None:
        return ""
    return _role_text(entry, "user")


def _assistant_text(entry: TranscriptEntry) -> str:
    return _role_text(entry, "assistant")


def _role_text(entry: TranscriptEntry, role: str) -> str:
    for message in reversed(entry.messages):
        if message.get("role") != role:
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return ""


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _int_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


__all__ = [
    "active_context_entries",
    "build_compaction_draft",
    "compactable_context_entries",
    "estimate_context_tokens",
]
