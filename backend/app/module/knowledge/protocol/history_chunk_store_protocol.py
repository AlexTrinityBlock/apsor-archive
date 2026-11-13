"""Persistence contract for conversation-history windows.

The agent slice owns message discovery and text extraction; this knowledge-side
contract owns the shared flat chunk index. Keeping the boundary here means the
agent indexer never imports ``ChunkModel`` or ``ChunkRepository`` directly, and
all writes still flow through ``IndexerService``.
"""

from collections.abc import Sequence
from typing import Protocol

from app.module.knowledge.domain.chunking_domain import ChunkDraft


class HistoryChunkStoreProtocol(Protocol):
    """Write and inspect one owner's history chunks."""

    async def existing_source_ids(self, source_ids: Sequence[int]) -> set[int]: ...

    async def replace_source(
        self,
        source_id: int,
        drafts: Sequence[ChunkDraft],
    ) -> int: ...

    async def mark_sources_not_current(self, source_ids: Sequence[int]) -> None: ...


__all__ = ["HistoryChunkStoreProtocol"]
