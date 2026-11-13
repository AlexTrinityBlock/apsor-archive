"""Flat, fixed-window indexing rules for past conversation messages.

Conversation memory is deliberately simple: raw text windows, no summaries,
extraction, hierarchy, or graph. Each window is at most 256 characters and
overlaps the next by 32 characters (stride 224), so a phrase that straddles a
window boundary remains retrievable from both sides. The only structure is the
stable ``agent_entry`` id attached to every window at retrieval time.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.module.agent.domain.agent_domain import KIND_ASSISTANT, KIND_USER
from app.shared.retrieval import (
    HISTORY_RESULT_LIMIT,
    HISTORY_RRF_K,
    HISTORY_VECTOR_RECALL_LIMIT,
    HISTORY_WINDOW_CHARS,
    HISTORY_WINDOW_OVERLAP_CHARS,
    HISTORY_WINDOW_STRIDE_CHARS,
)
from app.shared.text.ngram import count_terms

# A user message is capped at 32,000 characters by the API; the tool returns
# the full immutable message unless the run's own tool-result budget clips it.
HISTORY_MESSAGE_MAX_CHARS = 32_000
HISTORY_MESSAGE_NEIGHBOR_LIMIT = 5
HISTORY_INDEX_BATCH_SIZE = 100
HISTORY_INDEX_INTERVAL_SECONDS = 30

HISTORY_INDEXED_KINDS = (KIND_USER, KIND_ASSISTANT)


@dataclass(frozen=True)
class HistoryWindow:
    """One deterministic, 1-based searchable window of a message."""

    index: int
    content: str
    char_count: int
    token_count: int


@dataclass(frozen=True)
class HistoryMessage:
    """One user or assistant message as the history tool sees it."""

    entry_id: int
    conversation_id: int
    conversation_title: str
    role: str
    created_at: datetime
    content: str


@dataclass(frozen=True)
class HistoryMessageRead:
    """A focused message with bounded chronological neighbours."""

    target: HistoryMessage
    before: list[HistoryMessage]
    after: list[HistoryMessage]


def normalize_history_text(value: str) -> str:
    """Normalize line endings and remove characters that cannot be indexed."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return normalized.strip()


def history_windows(value: str) -> list[HistoryWindow]:
    """Split text into 256-character windows with a 32-character overlap.

    Text at or below one window becomes one window. Longer text walks the
    string in 224-character strides. The final window is only emitted when the
    previous one did not already reach the end, so a 256-character text does
    not grow a redundant tail window.
    """
    normalized = normalize_history_text(value)
    if not normalized:
        return []

    windows: list[str] = []
    if len(normalized) <= HISTORY_WINDOW_CHARS:
        windows.append(normalized)
    else:
        start = 0
        while start < len(normalized):
            windows.append(normalized[start : start + HISTORY_WINDOW_CHARS])
            if start + HISTORY_WINDOW_CHARS >= len(normalized):
                break
            start += HISTORY_WINDOW_STRIDE_CHARS

    return [
        HistoryWindow(
            index=index,
            content=window,
            char_count=len(window),
            token_count=count_terms(window),
        )
        for index, window in enumerate(
            (window for window in windows if window.strip()),
            start=1,
        )
    ]


def entry_message_text(
    kind: str,
    messages: Sequence[Mapping[str, Any]] | None,
) -> str:
    """Extract indexable text from one immutable transcript entry.

    Only the provider-facing text of a user or assistant message is indexed.
    Chat-image parts, tool calls, and UI-only data are not conversation text.
    """
    if kind not in HISTORY_INDEXED_KINDS or not messages:
        return ""
    for message in messages:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            return normalize_history_text(content)
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                part_type = part.get("type")
                text = part.get("text")
                if part_type in {None, "text"} and isinstance(text, str):
                    parts.append(text)
            return normalize_history_text("\n".join(parts))
        if isinstance(content, Mapping):
            text = content.get("text")
            if isinstance(text, str):
                return normalize_history_text(text)
    return ""


__all__ = [
    "HISTORY_INDEXED_KINDS",
    "HISTORY_INDEX_BATCH_SIZE",
    "HISTORY_INDEX_INTERVAL_SECONDS",
    "HISTORY_MESSAGE_MAX_CHARS",
    "HISTORY_MESSAGE_NEIGHBOR_LIMIT",
    "HISTORY_RESULT_LIMIT",
    "HISTORY_RRF_K",
    "HISTORY_VECTOR_RECALL_LIMIT",
    "HISTORY_WINDOW_CHARS",
    "HISTORY_WINDOW_OVERLAP_CHARS",
    "HISTORY_WINDOW_STRIDE_CHARS",
    "HistoryMessage",
    "HistoryMessageRead",
    "HistoryWindow",
    "entry_message_text",
    "history_windows",
    "normalize_history_text",
]
