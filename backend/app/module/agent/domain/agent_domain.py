"""Pure value objects for the immutable agent transcript.

The provider-facing ``model`` messages and the UI/diagnostic ``data`` payloads are
separate projections of the same append-only entry log. This module owns the
shared vocabulary and the validation of context edits; it performs no I/O.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

KIND_USER = "pi.user"
KIND_ASSISTANT = "pi.assistant"
KIND_TOOL_RESULT = "pi.tool-result"
KIND_PAGE_CONTEXT = "pi.page-context"
KIND_SYSTEM = "pi.system"
KIND_RESET = "pi.reset"
KIND_COMPACTION = "pi.compaction"
KIND_NOTICE = "ui.notice"

ENTRY_KINDS = (
    KIND_USER,
    KIND_ASSISTANT,
    KIND_TOOL_RESULT,
    KIND_PAGE_CONTEXT,
    KIND_SYSTEM,
    KIND_RESET,
    KIND_COMPACTION,
    KIND_NOTICE,
)

MODEL_REQUIRED_KINDS = (
    KIND_USER,
    KIND_ASSISTANT,
    KIND_TOOL_RESULT,
    KIND_PAGE_CONTEXT,
    KIND_SYSTEM,
)

MAX_PAGE_CONTEXT_CHARS = 6000

EDIT_ACTION_OMIT = "omit"
EDIT_ACTION_REPLACE = "replace"
EDIT_ACTIONS = (EDIT_ACTION_OMIT, EDIT_ACTION_REPLACE)

RUN_RUNNING = "running"
RUN_WAITING = "waiting"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

RUN_STATUSES = (
    RUN_RUNNING,
    RUN_WAITING,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_CANCELLED,
)
ACTIVE_RUN_STATUSES = (RUN_RUNNING, RUN_WAITING)
TERMINAL_RUN_STATUSES = (RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED)

CONVERSATION_ACTIVE = "active"
CONVERSATION_ARCHIVED = "archived"
CONVERSATION_STATUSES = (CONVERSATION_ACTIVE, CONVERSATION_ARCHIVED)

ERROR_FINISH_REASONS = frozenset({"error", "aborted", "cancelled", "canceled"})

MAX_STEPS = 24
MAX_TOOL_CALLS_PER_TURN = 6
MAX_PARALLEL_TOOLS = 6
# Model capability metadata, not a cost guard. The turn budget below remains the
# limit the loop enforces; compaction is still measured against that budget.
CONTEXT_WINDOW_TOKENS = 1_000_000
# One turn may use up to 100k provider tokens. Auto compaction triggers before a
# new user turn once the estimated active context reaches 75% of that budget.
MAX_TOTAL_TOKENS = 100_000
COMPACTION_THRESHOLD_TOKENS = 75_000
# Tool output stays on its own, smaller budget: every tool result is capped at
# 12k chars and each turn may emit at most 24k characters across all results.
MAX_TOOL_RESULT_CHARS = 100_000
MAX_COMPACTION_SUMMARY_CHARS = 6_000
MAX_COMPACTION_LAST_USER_CHARS = 4_000
AUTO_COMPACTION_ENABLED = True
PARALLEL_TOOLS_ENABLED = True
# Memory writes wait for an explicit user decision by default. The waiting and
# approval flow lives in the approval feature; this flag only stores whether the
# owner wants that gate enabled.
SAVE_MEMORY_REQUIRES_APPROVAL = True

EditAction = Literal["omit", "replace"]


@dataclass(frozen=True)
class ContextEdit:
    """One immutable context-only override attached to an entry."""

    target_entry_id: int
    action: EditAction
    messages: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class TranscriptEntry:
    """An entry in the form the context builder needs."""

    id: int
    kind: str
    messages: tuple[dict[str, Any], ...] = ()
    data: dict[str, Any] | list[Any] | None = None
    head_entry_id: int | None = None
    edits: tuple[ContextEdit, ...] = ()
    by_run_id: int | None = None


@dataclass(frozen=True)
class ProviderContext:
    """The exact provider request derived from the entry log."""

    system_message: dict[str, Any]
    tools: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    source_entry_ids: list[int]
    cache_prefix_hash: str


@dataclass(frozen=True)
class EntryDraft:
    """A new immutable entry before the repository assigns an id."""

    kind: str
    messages: list[dict[str, Any]]
    data: dict[str, Any] | list[Any] | None = None


@dataclass(frozen=True)
class AgentStreamEvent:
    """One transport event in an agent turn stream."""

    event: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolOutcome:
    """The normalized result of one tool execution."""

    content: str
    data: dict[str, Any]
    status: str = "ok"
    error_code: str | None = None
    resource: dict[str, Any] | None = None


def parse_edits(raw: object) -> tuple[ContextEdit, ...]:
    """Validate and normalize the JSONB ``edits`` array.

    Invalid stored edits are a consistency error; the caller translates the
    ``ValueError`` into an application error with a stable code.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("edits must be an array.")
    parsed: list[ContextEdit] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"edits[{index}] must be an object.")
        unknown = set(item) - {"target_entry_id", "action", "messages"}
        if unknown:
            raise ValueError(f"edits[{index}] has unknown keys: {', '.join(sorted(unknown))}.")
        target = item.get("target_entry_id")
        action = item.get("action")
        if not isinstance(target, int) or isinstance(target, bool) or target < 1:
            raise ValueError(f"edits[{index}].target_entry_id must be a positive integer.")
        if action not in EDIT_ACTIONS:
            raise ValueError(f"edits[{index}].action must be 'omit' or 'replace'.")
        raw_messages = item.get("messages", [])
        if action == EDIT_ACTION_OMIT:
            if raw_messages:
                raise ValueError(f"edits[{index}] cannot carry messages for omit.")
            parsed.append(ContextEdit(target_entry_id=target, action="omit"))
            continue
        if not isinstance(raw_messages, list):
            raise ValueError(f"edits[{index}].messages must be an array.")
        messages: list[dict[str, Any]] = []
        for message in raw_messages:
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                raise ValueError(f"edits[{index}].messages must contain role-bearing objects.")
            messages.append(dict(message))
        parsed.append(
            ContextEdit(
                target_entry_id=target,
                action="replace",
                messages=tuple(messages),
            )
        )
    return tuple(parsed)
