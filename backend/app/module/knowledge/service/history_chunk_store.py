"""Knowledge-side storage adapter for the conversation-history flat index.

The agent history indexer discovers immutable messages and builds fixed text
windows. This adapter deletes the previous windows for one entry and hands the
new drafts to the shared ``IndexerService``, so history uses the same chunk
schema, BM25 n-grams, embedding batches, and retry behaviour as files, memories,
and summaries.
"""

from collections.abc import Sequence

from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.model.chunk_model import SOURCE_HISTORY
from app.module.knowledge.protocol.chunk_repository_protocol import (
    ChunkRepositoryProtocol,
)
from app.module.knowledge.service.indexer_service import IndexerService


class HistoryChunkStore:
    """One owner's history rows, bound to one short-lived session."""

    def __init__(
        self,
        *,
        user_id: int,
        chunk_repository: ChunkRepositoryProtocol,
        indexer: IndexerService,
    ) -> None:
        self.user_id = user_id
        self.chunk_repository = chunk_repository
        self.indexer = indexer

    async def existing_source_ids(self, source_ids: Sequence[int]) -> set[int]:
        """Return entry ids that already own at least one history window."""
        return await self.chunk_repository.source_ids_present(
            SOURCE_HISTORY,
            source_ids,
        )

    async def replace_source(
        self,
        source_id: int,
        drafts: Sequence[ChunkDraft],
    ) -> int:
        """Replace every stored window for one immutable entry id."""
        await self.chunk_repository.delete_source(SOURCE_HISTORY, source_id)
        if not drafts:
            return 0
        return await self.indexer.index_chunks(
            source_kind=SOURCE_HISTORY,
            source_id=source_id,
            drafts=list(drafts),
            is_current=True,
        )

    async def mark_sources_not_current(self, source_ids: Sequence[int]) -> None:
        """Hide history windows whose conversation was deleted."""
        await self.chunk_repository.mark_sources_not_current(
            SOURCE_HISTORY,
            list(source_ids),
        )


__all__ = ["HistoryChunkStore"]
