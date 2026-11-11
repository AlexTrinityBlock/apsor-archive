"""HTTP contracts for temporary chat images."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentChatAttachmentStatus = Literal["staged", "attached"]

CLIENT_KEY_PATTERN = r"^[A-Za-z0-9_-]{16,64}$"


class AgentChatAttachmentSchema(BaseModel):
    """One temporary image owned by the authenticated account."""

    model_config = ConfigDict(frozen=True)

    id: int
    file_name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    status: AgentChatAttachmentStatus
    conversation_id: int | None
    entry_id: int | None
    created_at: datetime
    content_url: str


class AgentChatAttachmentCancelSchema(BaseModel):
    """Idempotently discard one staged upload by its browser token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_token: str = Field(
        min_length=16,
        max_length=64,
        pattern=CLIENT_KEY_PATTERN,
    )


__all__ = [
    "CLIENT_KEY_PATTERN",
    "AgentChatAttachmentCancelSchema",
    "AgentChatAttachmentSchema",
    "AgentChatAttachmentStatus",
]
