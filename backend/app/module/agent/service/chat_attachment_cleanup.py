"""Finite-lifetime cleanup for unsent chat images.

Discovery across owners uses the maintenance session only to read attachment
ids. Each row is then claimed and soft-deleted inside its owner's RLS-scoped
session; only after that claim succeeds is the object removed from storage.
Images attached to a message are durable and are never selected here.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from app.infrastructure.database.session import Database
from app.infrastructure.files.storage_errors import StorageError
from app.module.agent.protocol.chat_attachment_storage_protocol import (
    ChatAttachmentStorageProtocol,
)
from app.shared.time import utcnow

logger = logging.getLogger(__name__)


class ChatAttachmentCleanup:
    """Delete expired staged chat images in bounded batches."""

    def __init__(
        self,
        *,
        database: Database,
        storage: ChatAttachmentStorageProtocol,
        staged_ttl: timedelta,
        interval_seconds: int,
        batch_size: int = 200,
    ) -> None:
        self.database = database
        self.storage = storage
        self.staged_ttl = staged_ttl
        self.interval_seconds = max(1, interval_seconds)
        self.batch_size = max(1, batch_size)

    async def run_once(self) -> int:
        """Remove every currently due staged attachment, up to the batch size."""
        deleted = 0
        while True:
            now = utcnow()
            staged_before = now - self.staged_ttl
            refs = await self._expired_refs(
                staged_before=staged_before,
                limit=self.batch_size,
            )
            if not refs:
                break
            claimed = 0
            for attachment_id, user_id in refs:
                try:
                    row = await self._claim(
                        attachment_id,
                        user_id,
                        now=now,
                        staged_before=staged_before,
                    )
                except Exception:
                    logger.exception(
                        "chat attachment cleanup could not claim attachment_id=%s",
                        attachment_id,
                    )
                    continue
                if row is None:
                    continue
                claimed += 1
                deleted += 1
                storage_key, storage_backend = row
                try:
                    await self.storage.delete(
                        storage_key,
                        backend=storage_backend,
                    )
                except (StorageError, OSError) as exc:
                    # The row is already inaccessible. A lifecycle rule on the
                    # per-user chat-temp prefix can remove the orphan object.
                    logger.warning(
                        "chat attachment cleanup could not delete object attachment_id=%s "
                        "reason=%s",
                        attachment_id,
                        type(exc).__name__,
                    )
            if len(refs) < self.batch_size or claimed == 0:
                break
        if deleted:
            logger.info("chat attachment cleanup removed=%d", deleted)
        return deleted

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Run immediately, then once per interval until stopped or cancelled."""
        logger.info(
            "chat attachment cleanup started staged_ttl_hours=%s interval_seconds=%d",
            int(self.staged_ttl.total_seconds() // 3600),
            self.interval_seconds,
        )
        while stop_event is None or not stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("chat attachment cleanup failed")
            if stop_event is None:
                await asyncio.sleep(self.interval_seconds)
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def _expired_refs(
        self,
        *,
        staged_before: datetime,
        limit: int,
    ) -> list[tuple[int, int]]:
        """Discover due staged ids across owners without reading metadata."""
        async with self.database.maintenance_session() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, user_id
                        FROM agent_chat_attachment
                        WHERE deleted_at IS NULL
                          AND entry_id IS NULL
                          AND created_at < :staged_before
                        ORDER BY id
                        LIMIT :limit
                        """
                    ),
                    {"staged_before": staged_before, "limit": limit},
                )
            ).mappings().all()
        return [(int(row["id"]), int(row["user_id"])) for row in rows]

    async def _claim(
        self,
        attachment_id: int,
        user_id: int,
        *,
        now: datetime,
        staged_before: datetime,
    ) -> tuple[str, str] | None:
        """Soft-delete one due staged row in its owner's RLS context.

        The conditional update is the race guard: an image that is being claimed
        by a new message no longer has ``entry_id IS NULL`` and is left alone.
        The returned object is deleted only after this transaction commits.
        """
        async with self.database.user_session(user_id, "user") as session:
            result = await session.execute(
                text(
                    """
                    UPDATE agent_chat_attachment
                    SET deleted_at = :now
                    WHERE id = :attachment_id
                      AND user_id = :user_id
                      AND deleted_at IS NULL
                      AND entry_id IS NULL
                      AND created_at < :staged_before
                    RETURNING storage_key, storage_backend
                    """
                ),
                {
                    "now": now,
                    "attachment_id": attachment_id,
                    "user_id": user_id,
                    "staged_before": staged_before,
                },
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return str(row["storage_key"]), str(row["storage_backend"])


__all__ = ["ChatAttachmentCleanup"]
