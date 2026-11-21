"""Ingestion dispatch: notifier enqueue hooks and RabbitMQ ack/retry decisions.

No test connects to a broker. The notifier is a recording fake installed on
``app.state``; the consumer decision tests use a subclass that records retry
publications and fake messages that record ack/reject calls.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import maintenance_session
from app.infrastructure.queue.rabbitmq import (
    RabbitMQJobConsumer,
    RabbitMQJobNotifier,
    build_job_message,
)
from app.module.knowledge.dependencies import build_job_notifier
from app.module.knowledge.protocol.job_notifier_protocol import NullJobNotifier
from app.module.knowledge.repository.ingest_job_repository import (
    IngestJobRepository,
    RequeuedJob,
)
from app.shared.time import utcnow
from tests.helpers import create_text


class _RecordingNotifier:
    """Record notify calls and optionally fail like an unreachable broker."""

    def __init__(self, *, fail: bool = False) -> None:
        self.job_ids: list[int] = []
        self.fail = fail
        self.closed = False

    async def notify(self, job_id: int) -> None:
        self.job_ids.append(job_id)
        if self.fail:
            raise ConnectionError("broker unavailable")

    async def close(self) -> None:
        self.closed = True


class _FakeMessage:
    """Minimal delivery object that records its disposition."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = False
        self.rejected: list[bool] = []

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, *, requeue: bool) -> None:
        self.rejected.append(requeue)


class _RecordingConsumer(RabbitMQJobConsumer):
    """Consumer whose retry publication is recorded instead of sent."""

    def __init__(
        self,
        handler: Callable[[int], Awaitable[str]],
        *,
        max_dispatch_retries: int = 20,
    ) -> None:
        super().__init__(
            url="amqp://demo:demo@127.0.0.1/",
            handler=handler,
            exchange_name="test.ingest",
            queue_name="test.ingest.jobs",
            retry_queue_name="test.ingest.jobs.retry",
            max_dispatch_retries=max_dispatch_retries,
        )
        self.retries: list[tuple[int, int]] = []
        self.retry_failure: Exception | None = None

    async def _publish_retry(self, job_id: int, retry_count: int) -> None:
        if self.retry_failure is not None:
            raise self.retry_failure
        self.retries.append((job_id, retry_count))


class _ReconnectConsumer(RabbitMQJobConsumer):
    """Lose the message stream once, then stop cleanly on the next session."""

    def __init__(self) -> None:
        super().__init__(
            url="amqp://demo:demo@127.0.0.1/",
            handler=self._noop_handler,
            exchange_name="test.ingest",
            queue_name="test.ingest.jobs",
            retry_queue_name="test.ingest.jobs.retry",
            initial_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
        )
        self.attempts = 0

    @staticmethod
    async def _noop_handler(job_id: int) -> str:
        del job_id
        return "processed"

    async def _consume_until_stopped(self) -> None:
        self.attempts += 1
        if self.attempts == 1:
            raise ConnectionError("broker restarted")
        self._stop.set()


class _StalledNotifier(RabbitMQJobNotifier):
    """Notifier whose connection attempt outlives the publish bound."""

    def __init__(self) -> None:
        super().__init__(
            url="amqp://demo:demo@127.0.0.1/",
            exchange_name="test.ingest",
            queue_name="test.ingest.jobs",
            retry_queue_name="test.ingest.jobs.retry",
            publish_timeout_seconds=0.1,
        )

    async def _ensure_exchange(self) -> Any:
        await asyncio.sleep(5)
        raise AssertionError("the timeout should have cancelled this call")


def _upload(client: TestClient, path: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/files/async",
        data={"path": path},
        files={"file": ("dispatch.txt", b"Dispatch payload.", "text/plain")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _requeue_one(
    client: TestClient,
    job_id: int,
    stale_before: datetime,
) -> RequeuedJob | None:
    """Call the maintenance-only atomic requeue through the app's database."""

    async def run() -> RequeuedJob | None:
        async with maintenance_session(client.app.state.db.session_factory) as session:
            return await IngestJobRepository(session).requeue_one(
                job_id,
                stale_before=stale_before,
            )

    return client.portal.call(run)


def test_async_upload_notifies_the_created_job(client: TestClient) -> None:
    notifier = _RecordingNotifier()
    client.app.state.job_notifier = notifier

    job = _upload(client, "/dispatch/notified.txt")

    assert notifier.job_ids == [job["id"]]
    queued = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"


def test_notifier_failure_keeps_the_upload_queued(client: TestClient) -> None:
    notifier = _RecordingNotifier(fail=True)
    client.app.state.job_notifier = notifier

    job = _upload(client, "/dispatch/broker-down.txt")

    assert notifier.job_ids == [job["id"]]
    state = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert state.status_code == 200
    assert state.json()["status"] == "queued"
    # The row is the fallback contract: a retryable worker can still drain it.
    assert client.portal.call(client.app.state.ingest_worker.run_once) is True


def test_process_notified_job_claims_one_and_reports_terminal(
    client: TestClient,
) -> None:
    worker = client.app.state.ingest_worker
    job = _upload(client, "/dispatch/claimed.txt")

    assert client.portal.call(worker.process_notified_job, job["id"]) == "processed"
    state = client.get(f"/api/v1/files/ingest-jobs/{job['id']}").json()
    assert state["status"] == "ready"

    assert client.portal.call(worker.process_notified_job, job["id"]) == "terminal"
    assert client.portal.call(worker.process_notified_job, 2_000_000_000) == "missing"


def test_process_notified_job_retries_a_live_lease_and_recovers_a_stale_one(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    worker = client.app.state.ingest_worker
    job = _upload(client, "/dispatch/lease.txt")

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file_ingest_job SET status = 'parsing', attempts = 1, "
                "updated_at = now() WHERE id = :job_id"
            ),
            {"job_id": job["id"]},
        )
    # A fresh lease belongs to another worker; the consumer must use the retry
    # queue instead of stealing the row.
    assert client.portal.call(worker.process_notified_job, job["id"]) == "retry"

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file_ingest_job SET updated_at = now() - interval '1 hour' "
                "WHERE id = :job_id"
            ),
            {"job_id": job["id"]},
        )
    assert client.portal.call(worker.process_notified_job, job["id"]) == "processed"
    assert client.get(f"/api/v1/files/ingest-jobs/{job['id']}").json()["status"] == "ready"


def test_requeue_one_detaches_the_staged_file_atomically(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    source = create_text(client, "/dispatch/requeue-source.md", "Source content. " * 20)
    source_file_id = int(source["id"])
    job = _upload(client, "/dispatch/requeue.txt")

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file_ingest_job SET status = 'parsing', attempts = 1, "
                "file_id = :file_id, updated_at = now() - interval '1 hour' "
                "WHERE id = :job_id"
            ),
            {"file_id": source_file_id, "job_id": job["id"]},
        )

    stale_before = utcnow() - timedelta(seconds=300)
    result = _requeue_one(client, job["id"], stale_before)

    assert result is not None
    assert result.old_file_id == source_file_id
    assert result.user_id > 0

    with owner_engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT status, file_id, attempts FROM file_ingest_job "
                "WHERE id = :job_id"
            ),
            {"job_id": job["id"]},
        ).one()
    assert row.status == "queued"
    assert row.file_id is None
    assert row.attempts == 1

    # The same cutoff cannot requeue an already queued row a second time, so a
    # later caller cannot delete a file it no longer owns.
    assert _requeue_one(client, job["id"], stale_before) is None


@pytest.mark.parametrize("outcome", ["processed", "terminal", "missing"])
def test_consumer_acks_terminal_outcomes(outcome: str) -> None:
    async def handler(job_id: int) -> str:
        del job_id
        return outcome

    consumer = _RecordingConsumer(handler)
    message = _FakeMessage(b'{"job_id": 7, "retry_count": 0}')

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert message.acked is True
    assert message.rejected == []
    assert consumer.retries == []


def test_consumer_schedules_a_delayed_retry_for_the_retry_outcome() -> None:
    async def handler(job_id: int) -> str:
        del job_id
        return "retry"

    consumer = _RecordingConsumer(handler)
    message = _FakeMessage(b'{"job_id": 11, "retry_count": 3}')

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert consumer.retries == [(11, 4)]
    assert message.acked is True
    assert message.rejected == []


def test_consumer_converts_a_handler_crash_into_a_retry() -> None:
    async def handler(job_id: int) -> str:
        del job_id
        raise RuntimeError("worker crashed")

    consumer = _RecordingConsumer(handler)
    message = _FakeMessage(b'{"job_id": 12, "retry_count": 0}')

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert consumer.retries == [(12, 1)]
    assert message.acked is True
    assert message.rejected == []


def test_consumer_stops_retrying_at_the_dispatch_limit() -> None:
    async def handler(job_id: int) -> str:
        del job_id
        return "retry"

    consumer = _RecordingConsumer(handler, max_dispatch_retries=2)
    message = _FakeMessage(b'{"job_id": 13, "retry_count": 2}')

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert consumer.retries == []
    assert message.acked is True


def test_consumer_rejects_a_malformed_message_without_requeue() -> None:
    async def handler(job_id: int) -> str:
        del job_id
        return "processed"

    consumer = _RecordingConsumer(handler)
    message = _FakeMessage(b"not json")

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert message.acked is False
    assert message.rejected == [False]
    assert consumer.retries == []


def test_consumer_requeues_the_original_when_retry_scheduling_fails() -> None:
    async def handler(job_id: int) -> str:
        del job_id
        return "retry"

    consumer = _RecordingConsumer(handler)
    consumer.retry_failure = RuntimeError("channel closed")
    message = _FakeMessage(b'{"job_id": 14, "retry_count": 0}')

    asyncio.run(consumer._on_message(message))  # type: ignore[arg-type]

    assert message.acked is False
    assert message.rejected == [True]


def test_consumer_reconnects_after_a_stream_loss() -> None:
    consumer = _ReconnectConsumer()

    asyncio.run(asyncio.wait_for(consumer.run(), timeout=2))

    assert consumer.attempts == 2


def test_publisher_timeout_bounds_a_stalled_broker_connection() -> None:
    notifier = _StalledNotifier()

    started = time.monotonic()
    asyncio.run(notifier.notify(22))
    elapsed = time.monotonic() - started

    assert elapsed < 1.0


def test_dispatch_messages_are_persistent_json() -> None:
    message = build_job_message(21, 0)

    assert message.body == b'{"job_id":21,"retry_count":0}'
    assert message.content_type == "application/json"
    assert message.delivery_mode is not None
    assert int(message.delivery_mode) == 2


def test_notifier_requires_a_url_only_when_enabled(settings: Settings) -> None:
    disabled = settings.model_copy(update={"rabbitmq_enabled": False})
    assert isinstance(build_job_notifier(disabled), NullJobNotifier)

    enabled = settings.model_copy(
        update={"rabbitmq_enabled": True, "rabbitmq_url": None}
    )
    with pytest.raises(RuntimeError, match="APSOR_RABBITMQ_URL"):
        build_job_notifier(enabled)
