"""Persistence contract for temporary chat images."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.agent.model.agent_model import AgentChatAttachmentModel


class ChatAttachmentRepositoryProtocol(Protocol):
    """The repository surface used by the attachment service."""

    async def add(
        self,
        *,
        storage_key: str,
        storage_backend: str,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        width: int,
        height: int,
        content_hash: str,
        created_at: datetime,
    ) -> AgentChatAttachmentModel: ...

    async def get(self, attachment_id: int) -> AgentChatAttachmentModel | None: ...

    async def page(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentChatAttachmentModel], int]: ...

    async def mark_deleted(self, attachment_id: int, *, now: datetime) -> bool: ...

    async def update_storage(
        self,
        attachment_id: int,
        *,
        storage_key: str,
        storage_backend: str,
    ) -> bool: ...

    async def list_by_ids(
        self,
        attachment_ids: Sequence[int],
    ) -> list[AgentChatAttachmentModel]: ...


__all__ = ["ChatAttachmentRepositoryProtocol"]
