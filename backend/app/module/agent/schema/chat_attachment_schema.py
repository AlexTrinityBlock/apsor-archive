"""HTTP contracts for temporary chat images."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

AgentChatAttachmentStatus = Literal["staged", "attached"]


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


__all__ = ["AgentChatAttachmentSchema", "AgentChatAttachmentStatus"]
