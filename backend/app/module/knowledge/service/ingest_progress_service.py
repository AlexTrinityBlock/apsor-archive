"""Server-sent ingestion progress over an ephemeral Valkey subscription.

The durable job row is authoritative. The stream sends one snapshot from a
short owner session, then relays compact pub/sub events. If the broker is
unavailable or the subscription ends early, the same stream falls back to
one-second owner-scoped database polling until the job is terminal.

No request-scoped database session is opened here: every snapshot or fallback
read uses a fresh ``user_session`` and closes it before the next yield.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime

from app.infrastructure.database.session import Database, user_session
from app.module.knowledge.exception.domain_error import IngestJobNotFoundError
from app.module.knowledge.protocol.progress_bus_protocol import (
    ProgressBusProtocol,
    ProgressBusUnavailable,
)
from app.module.knowledge.repository.ingest_job_repository import IngestJobRepository
from app.module.knowledge.schema.file_schema import IngestProgressEventSchema

logger = logging.getLogger(__name__)

TERMINAL_INGEST_STATUSES = frozenset({"ready", "failed"})

# One browser tab can wait up to 30 minutes; keepalives only need to defeat
# proxy idle timeouts well inside that budget.
DEFAULT_KEEPALIVE_SECONDS = 15.0
DEFAULT_POLL_SECONDS = 1.0


def _frame(event_name: str, event: IngestProgressEventSchema) -> str:
    """Render one SSE frame with a compact JSON payload."""
    return f"event: {event_name}\ndata: {event.model_dump_json()}\n\n"


class IngestProgressService:
    """Snapshot, subscribe, and fall back for one owner's ingestion job."""

    def __init__(
        self,
        *,
        database: Database,
        progress_bus: ProgressBusProtocol,
        user_id: int,
        role: str,
        keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        self.database = database
        self.progress_bus = progress_bus
        self.user_id = user_id
        self.role = role
        self.keepalive_seconds = max(0.01, keepalive_seconds)
        self.poll_seconds = max(0.01, poll_seconds)

    async def _read(self, job_id: int) -> IngestProgressEventSchema | None:
        """Read one compact event through a fresh owner-scoped session."""
        async with user_session(
            self.database.session_factory,
            self.user_id,
            self.role,
        ) as session:
            job = await IngestJobRepository(session, self.user_id).get(job_id)
            if job is None:
                return None
            return IngestProgressEventSchema.model_validate(job)

    async def snapshot(self, job_id: int) -> IngestProgressEventSchema:
        """Return the current compact job or raise the stable not-found error."""
        event = await self._read(job_id)
        if event is None:
            raise IngestJobNotFoundError(job_id)
        return event

    async def stream(
        self,
        job_id: int,
        *,
        initial: IngestProgressEventSchema | None = None,
    ) -> AsyncIterator[str]:
        """Yield the snapshot plus progress frames until a terminal status.

        ``initial`` lets the route verify ownership before it starts the
        ``StreamingResponse``; tests may omit it and let the service read.
        """
        current = initial or await self.snapshot(job_id)
        yield _frame("snapshot", current)
        if current.status in TERMINAL_INGEST_STATUSES:
            return

        last_updated = current.updated_at
        try:
            async with self.progress_bus.subscribe(job_id) as events:
                # Close the publish gap between the snapshot and the
                # subscription with one short owner read. Without this, a job
                # that finished in that window could leave the stream idle.
                reconciled = await self._read(job_id)
                if reconciled is not None and reconciled.updated_at > last_updated:
                    last_updated = reconciled.updated_at
                    yield _frame("progress", reconciled)
                    if reconciled.status in TERMINAL_INGEST_STATUSES:
                        return
                async for event in self._events_with_keepalive(events):
                    if event is None:
                        yield ": keepalive\n\n"
                        continue
                    if event.updated_at <= last_updated:
                        # Pub/Sub is unordered across reconnects and publish
                        # retries; never move the stream backwards.
                        continue
                    last_updated = event.updated_at
                    yield _frame("progress", event)
                    if event.status in TERMINAL_INGEST_STATUSES:
                        return
        except ProgressBusUnavailable as exc:
            logger.debug(
                "Ingestion progress bus unavailable for job %d (%s); polling",
                job_id,
                type(exc).__name__,
            )
        except IngestJobNotFoundError:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Ingestion progress stream failed for job %d (%s); polling",
                job_id,
                type(exc).__name__,
            )

        async for event in self._poll_until_terminal(job_id, last_updated):
            yield _frame("progress", event)

    async def _events_with_keepalive(
        self,
        events: AsyncIterator[IngestProgressEventSchema],
    ) -> AsyncIterator[IngestProgressEventSchema | None]:
        """Relay bus events while emitting ``None`` on the keepalive cadence.

        A pump task owns the subscription iterator so a keepalive timeout never
        cancels the underlying ``listen`` call.
        """
        queue: asyncio.Queue[IngestProgressEventSchema | None] = asyncio.Queue()

        async def pump() -> None:
            try:
                async for event in events:
                    queue.put_nowait(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Ingestion progress subscription failed (%s)",
                    type(exc).__name__,
                )
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(pump())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(),
                        timeout=self.keepalive_seconds,
                    )
                except TimeoutError:
                    yield None
                    continue
                if item is None:
                    return
                yield item
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _poll_until_terminal(
        self,
        job_id: int,
        last_updated: datetime,
    ) -> AsyncIterator[IngestProgressEventSchema]:
        """Fallback polling: emit only changed snapshots until terminal."""
        while True:
            await asyncio.sleep(self.poll_seconds)
            try:
                event = await self._read(job_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Could not poll ingestion progress for job %d (%s)",
                    job_id,
                    type(exc).__name__,
                )
                continue
            if event is None:
                return
            if event.updated_at <= last_updated:
                continue
            last_updated = event.updated_at
            yield event
            if event.status in TERMINAL_INGEST_STATUSES:
                return


__all__ = [
    "DEFAULT_KEEPALIVE_SECONDS",
    "DEFAULT_POLL_SECONDS",
    "TERMINAL_INGEST_STATUSES",
    "IngestProgressService",
]
