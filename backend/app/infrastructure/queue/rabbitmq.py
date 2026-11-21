"""RabbitMQ dispatch adapter for durable ingestion jobs.

PostgreSQL ``file_ingest_job`` is the authoritative ledger; this module only
adds a low-latency wake-up path. A message carries the job id and a dispatch
retry count, never the payload or the job state. The worker re-reads and claims
the row, so a duplicated, late, or lost message can only cost latency: polling
remains the fallback.

Topology:

* durable direct exchange ``apsor.ingest``;
* durable classic queue ``apsor.ingest.jobs`` bound with routing key ``job``;
* durable classic retry queue ``apsor.ingest.jobs.retry`` bound with routing
  key ``retry``, a 30-second TTL, and dead-lettering back to the main queue.

The consumer uses manual acknowledgements and ``prefetch_count=1``: a process
crash leaves the delivery unacked, so RabbitMQ redelivers it and the worker
resumes or retries the job from its database row.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractRobustChannel,
    AbstractRobustConnection,
)

logger = logging.getLogger(__name__)

ROUTING_KEY = "job"
RETRY_ROUTING_KEY = "retry"

TERMINAL_OUTCOMES = frozenset({"processed", "terminal", "missing"})
RETRY_OUTCOME = "retry"

JobDispatchHandler = Callable[[int], Awaitable[str]]


def build_job_message(job_id: int, retry_count: int) -> Message:
    """Build one persistent JSON wake-up message; no archive content."""
    body = json.dumps(
        {"job_id": job_id, "retry_count": retry_count},
        separators=(",", ":"),
    ).encode("utf-8")
    return Message(
        body=body,
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        message_id=f"ingest-{job_id}",
    )


async def declare_ingest_topology(
    channel: AbstractChannel,
    *,
    exchange_name: str,
    queue_name: str,
    retry_queue_name: str,
    retry_ttl_ms: int,
) -> AbstractExchange:
    """Declare the exchange, main queue, and TTL retry queue idempotently.

    The publisher and the consumer both call this with the same arguments so
    either process may start first, and so a restart never hits a mismatched
    queue declaration.
    """
    exchange = await channel.declare_exchange(
        exchange_name,
        ExchangeType.DIRECT,
        durable=True,
    )
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={"x-queue-type": "classic"},
    )
    await queue.bind(exchange, routing_key=ROUTING_KEY)
    retry_queue = await channel.declare_queue(
        retry_queue_name,
        durable=True,
        arguments={
            "x-queue-type": "classic",
            "x-message-ttl": retry_ttl_ms,
            # The TTL expiry dead-letters the message back to the main queue,
            # where the consumer sees it with its incremented retry count.
            "x-dead-letter-exchange": exchange_name,
            "x-dead-letter-routing-key": ROUTING_KEY,
        },
    )
    await retry_queue.bind(exchange, routing_key=RETRY_ROUTING_KEY)
    return exchange


class RabbitMQJobNotifier:
    """Publish persistent wake-up messages with publisher confirms."""

    def __init__(
        self,
        *,
        url: str,
        exchange_name: str,
        queue_name: str,
        retry_queue_name: str,
        retry_ttl_ms: int = 30_000,
        connect_timeout_seconds: float = 5.0,
        publish_timeout_seconds: float = 1.0,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._retry_queue_name = retry_queue_name
        self._retry_ttl_ms = retry_ttl_ms
        self._connect_timeout_seconds = connect_timeout_seconds
        self._publish_timeout_seconds = max(0.1, publish_timeout_seconds)
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._connect_lock = asyncio.Lock()

    async def _ensure_exchange(self) -> AbstractExchange:
        """Return the cached exchange, connecting on first use or reconnecting."""
        exchange = self._exchange
        if exchange is not None and self._channel is not None and not self._channel.is_closed:
            return exchange
        async with self._connect_lock:
            exchange = self._exchange
            if (
                exchange is not None
                and self._channel is not None
                and not self._channel.is_closed
            ):
                return exchange
            connection = await aio_pika.connect_robust(
                self._url,
                timeout=self._connect_timeout_seconds,
            )
            try:
                channel = await connection.channel(
                    publisher_confirms=True,
                    on_return_raises=True,
                )
                exchange = await declare_ingest_topology(
                    channel,
                    exchange_name=self._exchange_name,
                    queue_name=self._queue_name,
                    retry_queue_name=self._retry_queue_name,
                    retry_ttl_ms=self._retry_ttl_ms,
                )
            except BaseException:
                await self._close_quietly(connection)
                raise
            self._connection = connection
            self._channel = channel
            self._exchange = exchange
            return exchange

    async def notify(self, job_id: int) -> None:
        """Publish one wake-up hint; a broker failure never fails the enqueue.

        Publishing is time-boxed: an upload must not wait for a full connection
        timeout when the broker is down. The database row is already the durable
        record, so a missed wake-up only costs one polling interval.
        """
        try:
            async with asyncio.timeout(self._publish_timeout_seconds):
                exchange = await self._ensure_exchange()
                await exchange.publish(
                    build_job_message(job_id, retry_count=0),
                    routing_key=ROUTING_KEY,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never log the AMQP URL or credentials; the type is enough to
            # distinguish a refused connection from a routing or confirm error.
            logger.warning(
                "Could not dispatch ingestion job %d to RabbitMQ (%s); "
                "database polling remains the fallback",
                job_id,
                type(exc).__name__,
            )
            await self._drop_connection()

    async def close(self) -> None:
        """Close the publisher connection during application shutdown."""
        connection, self._connection = self._connection, None
        self._channel = None
        self._exchange = None
        if connection is not None:
            await self._close_quietly(connection)

    async def _drop_connection(self) -> None:
        """Discard a failed connection so the next notify reconnects."""
        connection, self._connection = self._connection, None
        self._channel = None
        self._exchange = None
        if connection is not None:
            try:
                async with asyncio.timeout(self._publish_timeout_seconds):
                    await self._close_quietly(connection)
            except TimeoutError:
                # The reference is already dropped; the next notify reconnects.
                # Do not let a half-open socket extend the upload latency.
                pass

    @staticmethod
    async def _close_quietly(connection: AbstractRobustConnection) -> None:
        try:
            await connection.close()
        except Exception as exc:
            logger.debug(
                "Could not close the RabbitMQ publisher connection (%s)",
                type(exc).__name__,
            )


class RabbitMQJobConsumer:
    """Consume dispatches with manual ack, prefetch 1, and a TTL retry queue."""

    def __init__(
        self,
        *,
        url: str,
        handler: JobDispatchHandler,
        exchange_name: str,
        queue_name: str,
        retry_queue_name: str,
        retry_ttl_ms: int = 30_000,
        max_dispatch_retries: int = 20,
        connect_timeout_seconds: float = 5.0,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        self._url = url
        self._handler = handler
        self._exchange_name = exchange_name
        self._queue_name = queue_name
        self._retry_queue_name = retry_queue_name
        self._retry_ttl_ms = retry_ttl_ms
        self.max_dispatch_retries = max(0, max_dispatch_retries)
        self._connect_timeout_seconds = connect_timeout_seconds
        self._initial_backoff_seconds = max(0.1, initial_backoff_seconds)
        self._max_backoff_seconds = max(self._initial_backoff_seconds, max_backoff_seconds)
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Consume until cancelled, reconnecting with capped exponential backoff."""
        backoff = self._initial_backoff_seconds
        while not self._stop.is_set():
            try:
                await self._consume_until_stopped()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "RabbitMQ ingest consumer disconnected (%s); retrying in %.1fs",
                    type(exc).__name__,
                    backoff,
                )
            else:
                return
            if self._stop.is_set():
                return
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, self._max_backoff_seconds)

    async def _consume_until_stopped(self) -> None:
        connection = await aio_pika.connect_robust(
            self._url,
            timeout=self._connect_timeout_seconds,
        )
        self._connection = connection
        try:
            channel = await connection.channel(
                publisher_confirms=True,
                on_return_raises=True,
            )
            await channel.set_qos(prefetch_count=1)
            exchange = await declare_ingest_topology(
                channel,
                exchange_name=self._exchange_name,
                queue_name=self._queue_name,
                retry_queue_name=self._retry_queue_name,
                retry_ttl_ms=self._retry_ttl_ms,
            )
            queue = await channel.declare_queue(
                self._queue_name,
                durable=True,
                arguments={"x-queue-type": "classic"},
            )
            self._channel = channel
            self._exchange = exchange
            logger.info(
                "RabbitMQ ingest consumer started queue=%s prefetch=1",
                self._queue_name,
            )
            # Iterate the deliveries explicitly. ``consume()`` only registers a
            # callback and returns, so waiting on the stop event afterwards
            # would never notice a channel or broker loss. The iterator ends
            # when the channel closes; an unexpected end must surface to
            # ``run()`` so it reconnects with backoff.
            async with queue.iterator(no_ack=False) as iterator:
                async for message in iterator:
                    await self._on_message(message)
            if not self._stop.is_set():
                raise ConnectionError(
                    "The RabbitMQ ingest message stream ended unexpectedly."
                )
        finally:
            self._channel = None
            self._exchange = None
            self._connection = None
            await self._close_quietly(connection)

    async def close(self) -> None:
        """Stop consuming and close the connection during shutdown."""
        self._stop.set()
        connection, self._connection = self._connection, None
        if connection is not None:
            await self._close_quietly(connection)

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """Handle one delivery without ever acking before the handler returns."""
        parsed = self._parse_message(message)
        if parsed is None:
            logger.warning("Discarding a malformed RabbitMQ ingest dispatch message")
            await self._reject(message, requeue=False)
            return
        job_id, retry_count = parsed
        try:
            outcome = await self._handler(job_id)
        except asyncio.CancelledError:
            # Leave the delivery unacked: RabbitMQ redelivers it after a crash
            # or a shutdown, and the job row decides whether to resume.
            raise
        except Exception as exc:
            logger.warning(
                "Ingest dispatch handler failed for job %d (%s); scheduling a retry",
                job_id,
                type(exc).__name__,
            )
            await self._schedule_retry(message, job_id, retry_count)
            return
        if outcome in TERMINAL_OUTCOMES:
            await self._ack(message)
            return
        if outcome != RETRY_OUTCOME:
            logger.warning(
                "Unknown ingest dispatch outcome %r for job %d; scheduling a retry",
                outcome,
                job_id,
            )
        await self._schedule_retry(message, job_id, retry_count)

    async def _schedule_retry(
        self,
        message: AbstractIncomingMessage,
        job_id: int,
        retry_count: int,
    ) -> None:
        """Publish one delayed retry, then ack the original delivery."""
        if retry_count >= self.max_dispatch_retries:
            logger.warning(
                "Dropping ingest dispatch for job %d after %d broker retries; "
                "database polling remains the fallback",
                job_id,
                retry_count,
            )
            await self._ack(message)
            return
        try:
            await self._publish_retry(job_id, retry_count + 1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Could not schedule a broker retry for ingestion job %d (%s); "
                "requeueing the original delivery",
                job_id,
                type(exc).__name__,
            )
            await self._reject(message, requeue=True)
            return
        await self._ack(message)

    async def _publish_retry(self, job_id: int, retry_count: int) -> None:
        exchange = self._exchange
        if exchange is None:
            raise RuntimeError("The RabbitMQ ingest exchange is not ready.")
        await exchange.publish(
            build_job_message(job_id, retry_count),
            routing_key=RETRY_ROUTING_KEY,
        )

    @staticmethod
    def _parse_message(message: AbstractIncomingMessage) -> tuple[int, int] | None:
        """Return ``(job_id, retry_count)`` or ``None`` for an invalid body."""
        try:
            payload = json.loads(message.body)
            job_id = int(payload["job_id"])
            retry_count = int(payload.get("retry_count", 0))
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            return None
        if job_id <= 0 or retry_count < 0:
            return None
        return job_id, retry_count

    @staticmethod
    async def _ack(message: AbstractIncomingMessage) -> None:
        try:
            await message.ack()
        except Exception as exc:
            logger.warning(
                "Could not ack an ingest dispatch message (%s); "
                "RabbitMQ may redeliver it",
                type(exc).__name__,
            )

    @staticmethod
    async def _reject(message: AbstractIncomingMessage, *, requeue: bool) -> None:
        try:
            await message.reject(requeue=requeue)
        except Exception as exc:
            logger.warning(
                "Could not reject an ingest dispatch message (%s)",
                type(exc).__name__,
            )

    @staticmethod
    async def _close_quietly(connection: AbstractRobustConnection) -> None:
        with suppress(Exception):
            await connection.close()


__all__ = [
    "JobDispatchHandler",
    "RabbitMQJobConsumer",
    "RabbitMQJobNotifier",
    "build_job_message",
    "declare_ingest_topology",
]
