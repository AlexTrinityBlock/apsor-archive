"""Request and response contracts for the persistent archive agent."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AgentConversationStatus = Literal["active", "archived"]
AgentProvider = Literal["deepseek", "openai-compatible"]
AgentEntryKind = Literal[
    "pi.user",
    "pi.assistant",
    "pi.tool-result",
    "pi.page-context",
    "pi.system",
    "pi.reset",
    "pi.compaction",
    "ui.notice",
]
AgentRunStatus = Literal["running", "waiting", "completed", "failed", "cancelled"]
AgentApprovalStatus = Literal["pending", "approved", "rejected", "expired"]


class AgentConversationCreateSchema(BaseModel):
    """Create a transcript scope with one frozen system entry."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    provider: AgentProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)


class AgentConversationPatchSchema(BaseModel):
    """Rename or archive a conversation; metadata only."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: AgentConversationStatus | None = None


class AgentConversationForkSchema(BaseModel):
    """Create an independent copy of a transcript through an inclusive cutoff."""

    model_config = ConfigDict(extra="forbid")

    at_entry_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)


class AgentPageContextSchema(BaseModel):
    """A plain-text snapshot of the page the user is currently viewing."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=512)
    path: str = Field(min_length=1, max_length=1024)
    title: str | None = Field(default=None, max_length=300)
    text: str = Field(min_length=1, max_length=12_000)


class AgentMessageCreateSchema(BaseModel):
    """Append one user entry and start a run."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=32_000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    page_context: AgentPageContextSchema | None = None
    client_timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_+\-/]+$",
    )
    client_utc_offset_minutes: int | None = Field(default=None, ge=-840, le=840)


class AgentRetrySchema(BaseModel):
    """Retry the latest failed or cancelled run."""

    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class AgentConversationSchema(BaseModel):
    """Conversation metadata, never its prompt or tools."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    parent_conversation_id: int | None
    fork_at_entry_id: int | None
    title: str
    provider: str
    model: str
    provider_session_id: UUID
    status: AgentConversationStatus
    created_at: datetime
    updated_at: datetime
    last_entry_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None


class AgentEntrySchema(BaseModel):
    """One immutable transcript entry as returned by the API."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    conversation_id: int
    commit_seq: int
    kind: AgentEntryKind
    model: list[dict[str, Any]] | None
    data: dict[str, Any] | list[Any] | None
    head_entry_id: int | None
    edits: list[dict[str, Any]] | None
    by_run_id: int | None
    created_at: datetime


class AgentEntryPageSchema(BaseModel):
    """Forward pagination over the entry log."""

    model_config = ConfigDict(frozen=True)

    conversation_id: int
    total_results: int
    entries: list[AgentEntrySchema]
    next_after_id: int | None
    has_more: bool


class AgentConversationDetailSchema(AgentConversationSchema):
    """Conversation metadata plus the first entry page."""

    entries: list[AgentEntrySchema]
    entries_total: int
    entries_next_after_id: int | None
    entries_has_more: bool
    last_page_context_key: str | None = None


class AgentRunSchema(BaseModel):
    """Operational state for one user submission."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    conversation_id: int
    request_id: str | None
    user_entry_id: int
    status: AgentRunStatus
    abort_requested: bool
    last_entry_id: int | None
    error_code: str | None
    error_detail: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    api_calls: int


class AgentApprovalSchema(BaseModel):
    """A durable human decision awaiting resolution.

    ``arguments`` and ``preview`` are intentionally bounded, validated copies of
    the proposed write. ``resume_state`` never leaves the repository.
    """

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    conversation_id: int
    run_id: int
    tool_call_id: str
    tool_name: str
    status: AgentApprovalStatus
    arguments: dict[str, Any]
    preview: dict[str, Any]
    resolved_by_entry_id: int | None
    requested_at: datetime
    resolved_at: datetime | None
    created_at: datetime


class AgentTurnResultSchema(BaseModel):
    """The completed turn returned by the JSON fallback."""

    model_config = ConfigDict(frozen=True)

    run: AgentRunSchema
    user_entry: AgentEntrySchema
    entries: list[AgentEntrySchema]
    assistant_entry: AgentEntrySchema | None
    tool_results: list[AgentEntrySchema]
    answer: str | None
    usage: dict[str, int]
    error_code: str | None
    error_detail: str | None
    pending_approvals: list[AgentApprovalSchema] = Field(default_factory=list)


class AgentToolSchema(BaseModel):
    """One tool in the public catalog."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]
    requires_confirmation: bool


class AgentToolCatalogSchema(BaseModel):
    """The frozen catalog version and its tools."""

    model_config = ConfigDict(frozen=True)

    prompt_version: str
    tools_version: str
    tools: list[AgentToolSchema]
