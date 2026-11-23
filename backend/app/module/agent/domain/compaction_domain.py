"""Deterministic context estimation and compaction summaries.

Compaction never calls a provider. It estimates the active context from the
persisted entries and builds one bounded ``pi.compaction`` message. The entry's
``head_entry_id`` starts a new context segment, so the old prefix is hidden from
future requests without rewriting any immutable row.
"""

import json
import math
import re
from collections.abc import Sequence
from decimal import Decimal
from string import Formatter
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
    ProviderContext,
    TranscriptEntry,
)
from app.module.agent.domain.context_domain import (
    active_start_entry_id,
    build_context,
)
from app.module.agent.domain.xml_domain import TRUNCATION_MARKER, clip, xml_text

MAX_SUMMARY_ITEM_CHARS = 280
MAX_SUMMARY_ARGUMENT_CHARS = 80
MAX_SUMMARY_ARGUMENT_VALUES = 3
MAX_COMPACTION_CARRY_CHARS = 1_200
MAX_SUMMARY_ITEMS = 40
CHARS_PER_ESTIMATED_TOKEN = 3
# Fixed XML envelope sizes. The bounded path reserves these before spending the
# remaining characters on the carry line and the summary items.
_COMPACTION_ENVELOPE_CHARS = len("<compaction><summary></summary></compaction>")
_LAST_USER_ENVELOPE_CHARS = len("<last_user_input></last_user_input>")
# The operator-editable compaction template is a closed vocabulary. Literal
# braces must be doubled, and ``{max_output_tokens}`` is mandatory so the
# summary always states its bound.
_COMPACTION_TEMPLATE_FIELDS = frozenset(
    {
        "max_output_tokens",
        "max_output_chars",
        "max_items",
        "max_line_chars",
        "max_last_user_chars",
    }
)
_COMPACTION_CONTEXT_FIELDS = (
    "max_items",
    "max_line_chars",
    "max_last_user_chars",
)
_FORMATTER = Formatter()
_CITATION_PATTERN = re.compile(
    r"\[(?:(?:file|memory|summary):\d+(?:#\d+)?|history:\d+)\]"
)
# Primary argument keys for a concrete tool line. The first key that exists
# wins, so a tool line names what the call was actually asked to do. Unknown
# tools fall back to the first scalar argument in sorted key order.
_TOOL_ARGUMENT_KEYS: dict[str, tuple[str, ...]] = {
    "web_search": ("query",),
    "search_knowledge": ("query",),
    "history_message": ("query", "id"),
    "web_fetch": ("url",),
    "read_memory": ("id", "title", "query"),
    "read_file": ("id", "title", "query"),
    "calculate": ("expression",),
    "render_plot": ("title",),
}


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


def validate_compaction_template(template: str) -> None:
    """Reject a compaction template the renderer cannot substitute safely.

    Only the placeholders used by the default template are accepted. A literal
    brace must be doubled so a typo cannot be silently treated as text, and the
    output bound is mandatory because the summary must state its limit.
    """
    if not isinstance(template, str):
        raise ValueError("Compaction template must be a string.")
    try:
        parsed = list(_FORMATTER.parse(template))
    except ValueError as exc:
        raise ValueError("Compaction template has an unmatched brace.") from exc
    names: list[str] = []
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in _COMPACTION_TEMPLATE_FIELDS:
            raise ValueError(
                f"Compaction template has an unknown placeholder {{{field_name}}}."
            )
        if conversion or format_spec:
            raise ValueError(
                "Compaction template placeholders do not support conversions or "
                "format specifications."
            )
        names.append(field_name)
    if "max_output_tokens" not in names:
        raise ValueError(
            "Compaction template must contain the {max_output_tokens} placeholder."
        )


def render_compaction_prompt(
    template: str,
    *,
    max_output_tokens: int,
    chars_per_token: float = CHARS_PER_ESTIMATED_TOKEN,
    **context: int,
) -> str:
    """Render the deterministic compaction instruction for the next model.

    The character bound is derived from the token bound and the provider's
    characters-per-token ratio, so the instruction and the output clip always
    state the same limit. Rendering is pure: no provider, clock, or randomness.
    """
    validate_compaction_template(template)
    _validate_positive_int("max_output_tokens", max_output_tokens)
    _validate_chars_per_token(chars_per_token)
    unknown = set(context) - set(_COMPACTION_CONTEXT_FIELDS)
    if unknown:
        raise ValueError(
            "Compaction template has unknown context values: "
            f"{', '.join(sorted(unknown))}."
        )
    values = {
        "max_output_tokens": max_output_tokens,
        "max_output_chars": _char_budget(max_output_tokens, chars_per_token),
        "max_items": context.get("max_items", MAX_SUMMARY_ITEMS),
        "max_line_chars": context.get("max_line_chars", MAX_SUMMARY_ITEM_CHARS),
        "max_last_user_chars": context.get(
            "max_last_user_chars",
            MAX_COMPACTION_LAST_USER_CHARS,
        ),
    }
    for name in _COMPACTION_CONTEXT_FIELDS:
        _validate_positive_int(name, values[name])
    return template.format_map(values)


def estimate_context_tokens(
    entries: Sequence[TranscriptEntry],
    *,
    chars_per_token: float = CHARS_PER_ESTIMATED_TOKEN,
) -> int:
    """Estimate provider tokens without calling the provider.

    The estimate is intentionally conservative: a serialized character count at
    the caller's characters-per-token ratio, compared against the latest valid
    assistant usage. The larger value wins so the auto-compaction threshold
    cannot be bypassed by a terse usage report.
    """
    _validate_chars_per_token(chars_per_token)
    ordered = sorted(entries, key=lambda entry: entry.id)
    if not ordered:
        return 0
    char_estimate = estimate_provider_context_tokens(
        build_context(ordered),
        chars_per_token=chars_per_token,
    )

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


def estimate_provider_context_tokens(
    context: ProviderContext,
    *,
    strip_image_data: bool = False,
    chars_per_token: float = CHARS_PER_ESTIMATED_TOKEN,
) -> int:
    """Estimate tokens for an already-built system/tools/messages request.

    ``strip_image_data`` replaces inline base64 image URLs with a short
    placeholder before serializing. Compression estimates use the default, so
    their behavior is unchanged; the provider-only self block opts in because it
    runs after chat-image enrichment. ``chars_per_token`` is the primary model's
    catalog ratio, so an unknown or non-Claude model uses the conservative
    default.
    """
    _validate_chars_per_token(chars_per_token)
    messages = (
        _strip_image_data_urls(context.messages)
        if strip_image_data
        else context.messages
    )
    serialized = json.dumps(
        {
            "system": context.system_message,
            "tools": context.tools,
            "messages": messages,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return math.ceil(len(serialized) / chars_per_token)


IMAGE_DATA_PLACEHOLDER = "[image-data-url]"


def _strip_image_data_urls(value: Any) -> Any:
    """Return a copy with data-URL image payloads replaced by a placeholder."""
    if isinstance(value, dict):
        return {
            key: (
                IMAGE_DATA_PLACEHOLDER
                if key == "url"
                and isinstance(item, str)
                and item.startswith("data:")
                else _strip_image_data_urls(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_strip_image_data_urls(item) for item in value]
    return value


def build_compaction_draft(
    entries: Sequence[TranscriptEntry],
    *,
    reason: str,
    auto: bool,
    max_summary_chars: int = MAX_COMPACTION_SUMMARY_CHARS,
    max_last_user_chars: int = MAX_COMPACTION_LAST_USER_CHARS,
    target_tokens: int | None = None,
    chars_per_token: float = CHARS_PER_ESTIMATED_TOKEN,
) -> EntryDraft:
    """Build the provider message and UI data for one compaction entry.

    The summary and carried last-user-input caps come from the active runtime
    config snapshot; the defaults keep the pure builder usable in isolation.

    ``target_tokens`` is the output budget used by the overflow ladder. When it
    is set, whole items are kept newest-first until the rendered entry fits the
    budget, and the summary and carry line share the derived character cap.
    Omitting it preserves the original threshold-compaction output exactly.
    """
    compactable = compactable_context_entries(entries)
    last_user_entry = _last_user_entry(compactable)
    if target_tokens is None:
        selected = compactable[-MAX_SUMMARY_ITEMS:]
        omitted = len(compactable) - len(selected)
        lines: list[str] = []
        if omitted > 0:
            lines.append(f"[{omitted} earlier entries omitted]")
        lines.extend(_summary_lines(selected))
        summary = "\n".join(lines)
        if not summary:
            summary = "No active conversation content to compact."
        summary = clip(summary, max_summary_chars)
        last_user_text = (
            clip(_one_line(_user_text(last_user_entry)), max_last_user_chars)
            if last_user_entry is not None
            else ""
        )
    else:
        _validate_positive_int("target_tokens", target_tokens)
        _validate_chars_per_token(chars_per_token)
        budget_chars = _char_budget(target_tokens, chars_per_token)
        summary_cap = min(max_summary_chars, budget_chars)
        carry_cap = min(
            max_last_user_chars,
            summary_cap,
            max(
                0,
                budget_chars
                - _COMPACTION_ENVELOPE_CHARS
                - _LAST_USER_ENVELOPE_CHARS,
            ),
        )
        last_user_text = (
            _clip_budget(_one_line(_user_text(last_user_entry)), carry_cap)
            if last_user_entry is not None
            else ""
        )
        selected, summary = _bounded_summary(
            compactable,
            last_user_text=last_user_text,
            budget_chars=budget_chars,
            summary_cap=summary_cap,
        )

    return EntryDraft(
        kind=KIND_COMPACTION,
        messages=[
            {
                "role": "user",
                "content": _compaction_content(summary, last_user_text),
            }
        ],
        data={
            "reason": reason,
            "summary_chars": len(summary),
            "last_user_entry_id": (last_user_entry.id if last_user_entry is not None else None),
            "source_entry_ids": [entry.id for entry in selected],
            "auto": auto,
        },
    )


def _compaction_content(summary: str, last_user_text: str) -> str:
    """Render the provider-visible compaction message."""
    values: list[str] = ["<compaction>"]
    if last_user_text:
        values.append(f"<last_user_input>{xml_text(last_user_text)}</last_user_input>")
    values.append(f"<summary>{xml_text(summary)}</summary>")
    values.append("</compaction>")
    return "".join(values)


def _last_user_entry(compactable: Sequence[TranscriptEntry]) -> TranscriptEntry | None:
    """Return the newest user entry that carries text."""
    return next(
        (
            entry
            for entry in reversed(compactable)
            if entry.kind == KIND_USER and _user_text(entry)
        ),
        None,
    )


def _bounded_summary(
    compactable: Sequence[TranscriptEntry],
    *,
    last_user_text: str,
    budget_chars: int,
    summary_cap: int,
) -> tuple[list[TranscriptEntry], str]:
    """Keep the newest whole items while the rendered entry fits the budget.

    Items are dropped oldest-first, never split. If not even one item fits, the
    summary falls back to the omission notice, clipped to the remaining room.
    """
    candidates = list(compactable[-MAX_SUMMARY_ITEMS:])
    for count in range(len(candidates), -1, -1):
        selected = candidates[len(candidates) - count :] if count else []
        omitted = len(compactable) - count
        lines: list[str] = []
        if omitted > 0:
            lines.append(f"[{omitted} earlier entries omitted]")
        lines.extend(_summary_lines(selected))
        summary = "\n".join(lines)
        if count == 0:
            if not summary:
                summary = "No active conversation content to compact."
            overhead = len(_compaction_content("", last_user_text))
            available = max(0, budget_chars - overhead)
            return [], _clip_budget(summary, min(summary_cap, available))
        if len(summary) > summary_cap:
            continue
        if len(_compaction_content(summary, last_user_text)) <= budget_chars:
            return selected, summary
    return [], ""


def _summary_lines(entries: Sequence[TranscriptEntry]) -> list[str]:
    """Render selected entries into compact summary lines.

    Consecutive tool-result entries with the same tool, status, and error code
    collapse into one counted line. Grouping happens here, on the selected
    window, so a run split by the window boundary is merged only inside it.
    Non-tool entries always break a run.
    """
    lines: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        data = entry.data if isinstance(entry.data, dict) else {}
        if entry.kind == KIND_TOOL_RESULT:
            end = index + 1
            if _mergeable_tool_result(data):
                key = _tool_group_key(data)
                while end < len(entries):
                    candidate = entries[end]
                    candidate_data = (
                        candidate.data if isinstance(candidate.data, dict) else {}
                    )
                    if candidate.kind != KIND_TOOL_RESULT:
                        break
                    if not _mergeable_tool_result(candidate_data):
                        break
                    if _tool_group_key(candidate_data) != key:
                        break
                    end += 1
            lines.append(_tool_line(data, entries[index:end]))
            index = end
            continue
        line = _summary_line(entry)
        if line:
            lines.append(line)
        index += 1
    return lines


def _mergeable_tool_result(data: dict[str, Any]) -> bool:
    """Return whether a tool result may join an identical consecutive run.

    A failed call stays individually visible and never joins a run.
    """
    if data.get("error_code"):
        return False
    return str(data.get("status") or "unknown") != "error"


def _tool_group_key(data: dict[str, Any]) -> tuple[str, str, str]:
    """Return the fields that must match for two tool results to merge."""
    return (
        str(data.get("tool") or "tool"),
        str(data.get("status") or "unknown"),
        str(data.get("error_code") or ""),
    )


def _tool_line(
    data: dict[str, Any],
    run: Sequence[TranscriptEntry],
) -> str:
    """Render one tool result, or one merged run of identical results."""
    name = str(data.get("tool") or "tool")
    status = str(data.get("status") or "unknown")
    error_code = data.get("error_code")
    label = f"Tool {name}"
    if len(run) > 1:
        label += f" ×{len(run)}"
    if error_code:
        return _clip_inline(
            f"{label}: {status} — code={error_code}",
            MAX_SUMMARY_ITEM_CHARS,
        )
    if status == "error":
        return _clip_inline(f"{label}: {status}", MAX_SUMMARY_ITEM_CHARS)
    values = _tool_argument_values(name, run)
    if not values:
        return _clip_inline(f"{label}: {status}", MAX_SUMMARY_ITEM_CHARS)
    return _clip_inline(
        f"{label}: {status} — {' | '.join(values)}",
        MAX_SUMMARY_ITEM_CHARS,
    )


def _tool_argument_values(
    name: str,
    run: Sequence[TranscriptEntry],
) -> list[str]:
    """Return distinct concrete arguments from a merged run, capped.

    Identical values are shown once; after three distinct values the line
    reports how many more were folded away.
    """
    values: list[str] = []
    seen: set[str] = set()
    for entry in run:
        data = entry.data if isinstance(entry.data, dict) else {}
        value = _tool_argument_value(name, data)
        if value is None or value in seen:
            continue
        seen.add(value)
        values.append(value)
    if len(values) > MAX_SUMMARY_ARGUMENT_VALUES:
        extra = len(values) - MAX_SUMMARY_ARGUMENT_VALUES
        return [*values[:MAX_SUMMARY_ARGUMENT_VALUES], f"+{extra} more"]
    return values


def _tool_argument_value(name: str, data: dict[str, Any]) -> str | None:
    """Pick one bounded, concrete argument value for a tool line."""
    arguments = data.get("arguments")
    if not isinstance(arguments, dict):
        return None
    if name == "present_resource":
        resource_type = _scalar_text(arguments.get("resource_type"))
        resource_id = _scalar_text(arguments.get("resource_id"))
        if resource_type and resource_id:
            return f"{resource_type}#{resource_id}"
        return resource_type or resource_id
    if name == "save_memory":
        title = _scalar_text(arguments.get("title"))
        if title:
            return _quote_argument(title)
        content = arguments.get("content")
        if isinstance(content, str):
            first_line = next(
                (line for line in content.splitlines() if line.strip()),
                "",
            )
            text = _scalar_text(first_line)
            if text:
                return _quote_argument(text)
        return None
    keys = _TOOL_ARGUMENT_KEYS.get(name)
    if keys is not None:
        for key in keys:
            value = _scalar_text(arguments.get(key))
            if value is None:
                continue
            if key == "id":
                return f"id={value}"
            return _quote_argument(value)
        return None
    for key in sorted(key for key in arguments if isinstance(key, str)):
        value = _scalar_text(arguments[key])
        if value is not None:
            return f"{key}={_quote_argument(value)}"
    return None


def _scalar_text(value: Any) -> str | None:
    """Return a bounded one-line scalar, or ``None`` for unusable values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None
    text = _one_line(value)
    if not text:
        return None
    return _clip_inline(text, MAX_SUMMARY_ARGUMENT_CHARS)


def _quote_argument(value: str) -> str:
    return f'"{value}"'


def _clip_inline(value: str, limit: int) -> str:
    """Clip to a hard character budget without introducing a new line."""
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit == 1:
        return "…"
    return value[: limit - 1].rstrip() + "…"


def _summary_line(entry: TranscriptEntry) -> str:
    """Render one non-tool entry, or an empty string when it has no content."""
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
        return f"Assistant: {text}{suffix}" if text else ""
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


def _validate_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def _validate_chars_per_token(chars_per_token: float) -> None:
    if not isinstance(chars_per_token, (int, float)) or isinstance(chars_per_token, bool):
        raise ValueError("chars_per_token must be a number.")
    if not math.isfinite(chars_per_token) or chars_per_token <= 0:
        raise ValueError("chars_per_token must be a positive finite number.")


def _char_budget(tokens: int, chars_per_token: float) -> int:
    """Return the integer character allowance for a token budget.

    ``Decimal(str(...))`` keeps catalog ratios such as 2.3 exact, so the default
    2,600-token cap reads 5,980 characters instead of a binary-float 5,979.
    """
    ratio = Decimal(str(chars_per_token))
    return max(1, math.floor(Decimal(tokens) * ratio))


def _clip_budget(value: str, limit: int) -> str:
    """Clip to a hard character budget, even below the truncation marker."""
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= len(TRUNCATION_MARKER):
        return ""
    return clip(value, limit)


def _int_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


__all__ = [
    "active_context_entries",
    "build_compaction_draft",
    "compactable_context_entries",
    "estimate_context_tokens",
    "estimate_provider_context_tokens",
    "render_compaction_prompt",
    "validate_compaction_template",
]
