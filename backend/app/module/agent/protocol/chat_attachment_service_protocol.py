"""The attachment surface consumed by the agent turn loop."""

from collections.abc import Sequence
from typing import Protocol

from app.module.agent.domain.agent_domain import TranscriptEntry
from app.module.agent.domain.chat_attachment_domain import ChatAttachmentImage


class ChatAttachmentServiceProtocol(Protocol):
    """Resolve temporary images for a user entry and provider context."""

    async def prepare_for_message(
        self,
        attachment_ids: Sequence[int],
    ) -> list[ChatAttachmentImage]: ...

    async def enrich_transcript(
        self,
        entries: Sequence[TranscriptEntry],
    ) -> list[TranscriptEntry]: ...


__all__ = ["ChatAttachmentServiceProtocol"]
