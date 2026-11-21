"""Valkey Pub/Sub adapter for ephemeral ingestion progress.

The existing cache client is reused only as a connection factory: every
subscription owns a separate ``PubSub`` connection, so a connection in subscribe
mode is never used for normal cache commands. Nothing here is durable; the job
row remains the source of truth and the SSE service falls back to polling.

Credentials in the cache URL never reach a log line. Failures are reported by
exception type only.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.module.knowledge.protocol.progress_bus_protocol import (
    NullProgressBus,
    ProgressBusProtocol,
    ProgressBusUnavailable,
)
from app.module.knowledge.schema.file_schema import IngestProgressEventSchema

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "apsor:ingest:progress:"


def progress_channel(job_id: int) -> str:
    """Return the one channel name for a durable job."""
    return f"{CHANNEL_PREFIX}{job_id}"


class ValkeyProgressBus:
    """Publish and subscribe to compact ingestion-progress events."""

    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url, decode_responses=True)

    async def publish(self, event: IngestProgressEventSchema) -> None:
        """Publish one event without ever failing the ingestion job."""
        try:
            await self._client.publish(progress_channel(event.id), event.model_dump_json())
        except Exception as exc:
            logger.warning(
                "Could not publish ingestion progress for job %d (%s)",
                event.id,
                type(exc).__name__,
            )

    @asynccontextmanager
    async def subscribe(
        self,
        job_id: int,
    ) -> AsyncIterator[AsyncIterator[IngestProgressEventSchema]]:
        """Open one dedicated pub/sub connection for this subscriber."""
        pubsub = self._client.pubsub()
        try:
            await pubsub.subscribe(progress_channel(job_id))
        except Exception as exc:
            await self._close_pubsub(pubsub)
            raise ProgressBusUnavailable(
                "Could not subscribe to ingestion progress."
            ) from exc
        try:
            yield self._events(pubsub)
        finally:
            await self._close_pubsub(pubsub)

    async def _events(
        self,
        pubsub: PubSub,
    ) -> AsyncIterator[IngestProgressEventSchema]:
        """Decode only real message frames; malformed payloads are ignored."""
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if not isinstance(data, (str, bytes)):
                    continue
                try:
                    yield IngestProgressEventSchema.model_validate_json(data)
                except Exception as exc:
                    logger.warning(
                        "Ignoring malformed ingestion progress event (%s)",
                        type(exc).__name__,
                    )
        except Exception as exc:
            logger.warning(
                "Ingestion progress subscription ended (%s)",
                type(exc).__name__,
            )

    async def _close_pubsub(self, pubsub: PubSub) -> None:
        with suppress(Exception):
            await pubsub.aclose()

    async def close(self) -> None:
        with suppress(Exception):
            await self._client.aclose()


def build_progress_bus(cache_url: str) -> ProgressBusProtocol:
    """Build a Valkey bus, or the null bus for memory-only deployments."""
    normalized = cache_url.strip().lower()
    if not normalized or normalized in {"memory://", "none"}:
        return NullProgressBus()
    return ValkeyProgressBus(cache_url)


__all__ = [
    "CHANNEL_PREFIX",
    "ValkeyProgressBus",
    "build_progress_bus",
    "progress_channel",
]
