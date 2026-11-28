"""Background backfill for file thumbnails.

Files ingested before thumbnails existed, rows rendered by an older generator,
and earlier failures below the attempt limit are discovered by id across owners
in a maintenance session that returns ids only, never names or content. Each
file is then processed in its owner's RLS session through ``FileService``.

The cursor lives in memory. When a scan reaches the end it restarts from id 0
on the next cycle, so a transient storage failure is retried later and a
restart is always safe: a missing row is the to-do list.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.knowledge.domain.thumbnail_domain import (
    GENERATOR_VERSION,
    MAX_THUMBNAIL_ATTEMPTS,
    THUMBNAIL_EXTENSIONS,
)
from app.module.knowledge.exception.domain_error import KnowledgeError

logger = logging.getLogger(__name__)

THUMBNAIL_BACKFILL_BATCH_SIZE = 50
THUMBNAIL_BACKFILL_INTERVAL_SECONDS = 60


class ThumbnailBackfillTarget(Protocol):
    async def backfill_thumbnail(self, file_id: int) -> bool: ...


ThumbnailServiceFactory = Callable[[AsyncSession, int], Awaitable[ThumbnailBackfillTarget]]


@dataclass(frozen=True)
class ThumbnailBackfillBatch:
    """Outcome of one discovery batch."""

    examined: int
    processed: int


class FileThumbnailBackfill:
    """Create missing or outdated thumbnails for every account's files."""

    def __init__(
        self,
        *,
        database: Database,
        service_factory: ThumbnailServiceFactory,
        batch_size: int = THUMBNAIL_BACKFILL_BATCH_SIZE,
        interval_seconds: int = THUMBNAIL_BACKFILL_INTERVAL_SECONDS,
        user_id: int | None = None,
        regenerate: bool = False,
    ) -> None:
        self.database = database
        self.service_factory = service_factory
        self.batch_size = max(1, batch_size)
        self.interval_seconds = max(1, interval_seconds)
        self.user_id = user_id
        self.regenerate = regenerate
        self._after_id = 0

    async def drain(self) -> int:
        """Process batches until one full scan finds nothing to do."""
        self._after_id = 0
        processed = 0
        while True:
            batch = await self.run_once()
            processed += batch.processed
            if batch.examined == 0:
                return processed

    async def count_candidates(self) -> int:
        """Count every file that the next full scan would process."""
        self._after_id = 0
        total = 0
        while True:
            refs = await self.candidates(limit=500)
            if not refs:
                self._after_id = 0
                return total
            total += len(refs)
            self._after_id = max(file_id for file_id, _ in refs)

    async def run_once(self) -> ThumbnailBackfillBatch:
        """Process one batch of candidates after the in-memory cursor."""
        refs = await self.candidates(limit=self.batch_size)
        if not refs:
            self._after_id = 0
            return ThumbnailBackfillBatch(examined=0, processed=0)
        processed = 0
        for file_id, user_id in refs:
            if await self._process(file_id, user_id):
                processed += 1
        self._after_id = max(file_id for file_id, _ in refs)
        return ThumbnailBackfillBatch(examined=len(refs), processed=processed)

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Backfill continuously, sleeping only when a scan comes back empty."""
        logger.info("file thumbnail backfill started")
        while stop_event is None or not stop_event.is_set():
            try:
                batch = await self.run_once()
            except Exception:
                logger.exception("file thumbnail backfill failed")
                batch = ThumbnailBackfillBatch(examined=0, processed=0)
            if batch.processed:
                logger.info("file thumbnail backfill processed=%s", batch.processed)
            if batch.examined > 0:
                await asyncio.sleep(0)
                continue
            if stop_event is None:
                await asyncio.sleep(self.interval_seconds)
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def candidates(self, *, limit: int) -> list[tuple[int, int]]:
        """Discover the next file ids that need a thumbnail, without content."""
        statement = text(
            """
            SELECT f.id, f.user_id
            FROM file f
            LEFT JOIN file_thumbnail t ON t.file_id = f.id
            WHERE f.id > :after_id
              AND f.deleted_at IS NULL
              AND f.storage_key IS NOT NULL
              AND lower(f.extension) = ANY(:extensions)
              AND (CAST(:user_id AS bigint) IS NULL OR f.user_id = CAST(:user_id AS bigint))
              AND (
                t.file_id IS NULL
                OR t.generator_version < :generator_version
                OR (t.status = 'failed' AND t.attempts < :max_attempts)
                OR CAST(:regenerate AS boolean)
              )
            ORDER BY f.id
            LIMIT :limit
            """
        )
        parameters: dict[str, object] = {
            "after_id": self._after_id,
            "extensions": sorted(THUMBNAIL_EXTENSIONS),
            "generator_version": GENERATOR_VERSION,
            "max_attempts": MAX_THUMBNAIL_ATTEMPTS,
            "limit": limit,
            "user_id": self.user_id,
            "regenerate": self.regenerate,
        }
        async with self.database.maintenance_session() as session:
            rows = (await session.execute(statement, parameters)).all()
        return [(int(row[0]), int(row[1])) for row in rows]

    async def _process(self, file_id: int, user_id: int) -> bool:
        try:
            async with self.database.user_session(user_id, "user") as session:
                service = await self.service_factory(session, user_id)
                if self.regenerate:
                    await session.execute(
                        text("DELETE FROM file_thumbnail WHERE file_id = :file_id"),
                        {"file_id": file_id},
                    )
                return await service.backfill_thumbnail(file_id)
        except asyncio.CancelledError:
            raise
        except KnowledgeError as exc:
            # Storage outages are transient; the next scan retries the file.
            logger.warning(
                "thumbnail backfill skipped file_id=%s reason=%s",
                file_id,
                type(exc).__name__,
            )
            return False
