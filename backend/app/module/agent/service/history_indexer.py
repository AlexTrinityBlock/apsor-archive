"""Background indexer for the conversation-history flat index.

New and existing ``pi.user`` / ``pi.assistant`` entries are discovered by id
across owners using a maintenance session that returns only ids. Each owner's
messages are then read and indexed inside that owner's RLS session. Text is cut
into fixed 256-character windows and written through the knowledge-side
``HistoryChunkStore``, so the shared chunk/BM25/embedding pipeline is reused.

The indexer is in-memory cursor based. On process start it rescans from id 0;
already-indexed entries are skipped, so a restart is safe and a first deployment
backfills every past conversation. Deleted conversations are reconciled in the
same loop and their windows are marked non-current.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.agent.domain.history_domain import (
    HISTORY_INDEX_BATCH_SIZE,
    HISTORY_INDEX_INTERVAL_SECONDS,
    entry_message_text,
    history_windows,
)
from app.module.agent.repository.history_repository import AgentHistoryRepository
from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.history_chunk_store_protocol import (
    HistoryChunkStoreProtocol,
)
from app.module.knowledge.service.cache_keys import user_version_scope

logger = logging.getLogger(__name__)

HistoryStoreFactory = Callable[[AsyncSession, int], HistoryChunkStoreProtocol]


@dataclass(frozen=True)
class HistoryIndexBatch:
    """Outcome of one discovery batch."""

    examined: int
    indexed: int


class AgentHistoryIndexer:
    """Index immutable conversation messages into the shared chunk table."""

    def __init__(
        self,
        *,
        database: Database,
        store_factory: HistoryStoreFactory,
        cache: CacheProtocol,
        batch_size: int = HISTORY_INDEX_BATCH_SIZE,
        interval_seconds: int = HISTORY_INDEX_INTERVAL_SECONDS,
    ) -> None:
        self.database = database
        self.store_factory = store_factory
        self.cache = cache
        self.batch_size = max(1, batch_size)
        self.interval_seconds = max(1, interval_seconds)
        self._after_id = 0
        self._seen_deleted: set[int] = set()

    async def drain(self) -> int:
        """Process batches until no candidate entries remain (used by tests)."""
        indexed = 0
        while True:
            batch = await self.run_once()
            indexed += batch.indexed
            if batch.examined == 0:
                return indexed

    async def run_once(self) -> HistoryIndexBatch:
        """Reconcile deleted conversations, then index one batch of messages."""
        await self._reconcile_deleted()
        refs = await self._candidate_refs(limit=self.batch_size)
        if not refs:
            return HistoryIndexBatch(examined=0, indexed=0)

        grouped: dict[int, list[int]] = defaultdict(list)
        for entry_id, user_id in refs:
            grouped[user_id].append(entry_id)

        indexed = 0
        for user_id, entry_ids in grouped.items():
            indexed += await self._index_owner(user_id, entry_ids)

        self._after_id = max(self._after_id, max(entry_id for entry_id, _ in refs))
        return HistoryIndexBatch(examined=len(refs), indexed=indexed)

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Index continuously, sleeping only when the candidate stream is empty."""
        logger.info("conversation history indexer started")
        while stop_event is None or not stop_event.is_set():
            try:
                batch = await self.run_once()
            except Exception:
                logger.exception("conversation history indexer failed")
                batch = HistoryIndexBatch(examined=0, indexed=0)
            if batch.examined > 0:
                await asyncio.sleep(0)
                continue
            if stop_event is None:
                await asyncio.sleep(self.interval_seconds)
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except TimeoutError:
                pass

    async def _candidate_refs(self, *, limit: int) -> list[tuple[int, int]]:
        """Discover the next entry ids without reading archive content."""
        async with self.database.maintenance_session() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT e.id, e.user_id
                        FROM agent_entry e
                        JOIN agent_conversation c
                          ON c.id = e.conversation_id
                         AND c.user_id = e.user_id
                        WHERE e.id > :after_id
                          AND e.kind IN ('pi.user', 'pi.assistant')
                          AND c.deleted_at IS NULL
                        ORDER BY e.id
                        LIMIT :limit
                        """
                    ),
                    {"after_id": self._after_id, "limit": limit},
                )
            ).mappings().all()
        return [(int(row["id"]), int(row["user_id"])) for row in rows]

    async def _index_owner(self, user_id: int, entry_ids: list[int]) -> int:
        indexed = 0
        async with self.database.user_session(user_id, "user") as session:
            repository = AgentHistoryRepository(session, user_id=user_id)
            entries = await repository.get_entries(entry_ids)
            if not entries:
                return 0
            store = self.store_factory(session, user_id)
            present = await store.existing_source_ids([entry.id for entry in entries])
            pending: list[tuple[int, list[ChunkDraft]]] = []
            for entry in entries:
                if entry.id in present:
                    continue
                text_value = entry_message_text(entry.kind, entry.model)
                drafts = [
                    ChunkDraft(
                        index=window.index,
                        content=window.content,
                        char_count=window.char_count,
                        token_count=window.token_count,
                    )
                    for window in history_windows(text_value)
                ]
                if not drafts:
                    # Empty assistant messages are valid transcript entries
                    # (tool-call-only turns). They have no searchable text.
                    continue
                pending.append((entry.id, drafts))
            if pending:
                await store.replace_many(pending)
                indexed += len(pending)
        if indexed:
            await self._bump(user_id)
        return indexed

    async def _reconcile_deleted(self) -> None:
        """Hide windows for conversations whose transcript was soft-deleted.

        This queries every deleted conversation id each cycle rather than a
        monotonically increasing cursor. A conversation can be created long
        before it is deleted, so a cursor would miss a low id deleted later.
        The query returns only ids; the owner context performs the update.
        """
        refs = await self._deleted_refs()
        for conversation_id, user_id in refs:
            if conversation_id in self._seen_deleted:
                continue
            try:
                async with self.database.user_session(user_id, "user") as session:
                    repository = AgentHistoryRepository(session, user_id=user_id)
                    entry_ids = await repository.conversation_entry_ids(conversation_id)
                    if entry_ids:
                        store = self.store_factory(session, user_id)
                        await store.mark_sources_not_current(entry_ids)
                self._seen_deleted.add(conversation_id)
                await self._bump(user_id)
            except Exception:
                logger.exception(
                    "history indexer could not retire conversation_id=%s",
                    conversation_id,
                )

    async def _deleted_refs(self) -> list[tuple[int, int]]:
        async with self.database.maintenance_session() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT c.id, c.user_id
                        FROM agent_conversation c
                        WHERE c.deleted_at IS NOT NULL
                        ORDER BY c.id
                        """
                    )
                )
            ).mappings().all()
        return [(int(row["id"]), int(row["user_id"])) for row in rows]

    async def _bump(self, user_id: int) -> None:
        try:
            await self.cache.bump_version(user_version_scope(user_id))
        except Exception:
            logger.warning(
                "history indexer could not invalidate search cache user_id=%s",
                user_id,
            )


__all__ = ["AgentHistoryIndexer", "HistoryIndexBatch", "HistoryStoreFactory"]
