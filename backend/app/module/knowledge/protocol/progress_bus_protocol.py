"""Ephemeral progress pub/sub port for durable ingestion jobs.

``file_ingest_job`` remains the source of truth. A progress event is only a
low-latency hint for an open browser stream, so a lost or duplicated message
costs a UI update and never changes job state. The null bus is used when the
cache URL is memory-only or dispatch is deliberately disabled.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.module.knowledge.schema.file_schema import IngestProgressEventSchema


class ProgressBusUnavailable(RuntimeError):
    """The progress bus is not configured or its subscription failed.

    Callers treat this as a reason to fall back to short database polling; it
    must never fail the durable ingestion job itself.
    """


class ProgressBusProtocol(Protocol):
    """Publish and subscribe to compact ingestion-progress events."""

    async def publish(self, event: IngestProgressEventSchema) -> None:
        """Publish one event. Implementations must not raise on a broken broker."""
        ...

    def subscribe(
        self,
        job_id: int,
    ) -> AbstractAsyncContextManager[AsyncIterator[IngestProgressEventSchema]]:
        """Open one dedicated subscription for a job.

        Each call needs its own pub/sub connection; a connection in subscribe
        mode must never be reused for ordinary cache commands.
        """
        ...

    async def close(self) -> None:
        """Release the publisher connection, if any."""
        ...


class NullProgressBus:
    """No-op publisher for memory-only deployments and tests."""

    async def publish(self, event: IngestProgressEventSchema) -> None:
        del event

    def subscribe(
        self,
        job_id: int,
    ) -> AbstractAsyncContextManager[AsyncIterator[IngestProgressEventSchema]]:
        raise ProgressBusUnavailable(
            f"Live ingestion progress is unavailable for job {job_id}."
        )

    async def close(self) -> None:
        return None


__all__ = [
    "NullProgressBus",
    "ProgressBusProtocol",
    "ProgressBusUnavailable",
]
