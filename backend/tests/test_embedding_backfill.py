"""Pending embeddings survive provider outages and are filled in later.

Every test is offline: provider failures come from fake embedders or from
patching the hashing embedder to raise the same errors a hosted provider would
(429 insufficient quota, 503 outage, 400 bad input).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.embedding.hashing_embedder import HashingEmbedder
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.knowledge.dependencies import build_embedding_backfill
from app.module.knowledge.domain.embedding_backfill_domain import (
    BREAKER_MAX_SECONDS,
    MAX_EMBEDDING_FAILURES,
    CircuitBreaker,
    backoff_seconds,
    failure_code,
    is_per_chunk_failure,
)
from app.module.knowledge.exception.domain_error import EmbeddingProviderError
from app.module.knowledge.repository.chunk_repository import ChunkRepository
from app.module.knowledge.service.embedding_backfill import EmbeddingBackfill
from app.module.knowledge.service.embedding_backfill_status import (
    EmbeddingBackfillStatusService,
)
from tests.conftest import UserClient
from tests.helpers import create_memory

DIMENSION = 8


class _FakeEmbedder:
    """Deterministic embedder whose failure mode the test can switch."""

    model_name = "fake-embed"
    dimension = DIMENSION

    def __init__(self) -> None:
        self.error: int | None = None  # HTTP status to raise for every call.
        self.poison_marker: str | None = None  # Texts that fail with 400.
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise EmbeddingProviderError("simulated", status_code=self.error)
        if self.poison_marker is not None and any(self.poison_marker in value for value in texts):
            raise EmbeddingProviderError("bad input", status_code=400)
        return [[float(len(value) % 7 + 1)] * DIMENSION for value in texts]

    @property
    def embedded_texts(self) -> int:
        return sum(len(batch) for batch in self.calls)


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


_SOURCE_IDS = iter(range(9000, 99000))


def _insert_pending(
    engine: Engine, user_id: int, contents: list[str], kind: str = "memory"
) -> None:
    with engine.begin() as connection:
        for content in contents:
            connection.execute(
                text(
                    """
                    INSERT INTO chunk (user_id, source_kind, source_id, chunk_index,
                                       content, char_count, token_count, embedding,
                                       embedding_model, is_current, created_at, updated_at)
                    VALUES (:user_id, :kind, :source_id, 1, :content, :chars, 1, NULL,
                            NULL, true, now(), now())
                    """
                ),
                {
                    "user_id": user_id,
                    "kind": kind,
                    "source_id": next(_SOURCE_IDS),
                    "content": content,
                    "chars": len(content),
                },
            )


def _chunk_states(engine: Engine, user_id: int) -> list[tuple[str, bool, str | None, int]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT content, embedding IS NULL AS pending, embedding_model, "
                "embedding_failures FROM chunk WHERE user_id = :user_id ORDER BY id"
            ),
            {"user_id": user_id},
        ).all()
    return [(row.content, row.pending, row.embedding_model, row.embedding_failures) for row in rows]


def _backfill(
    client: TestClient,
    embedder: _FakeEmbedder,
    *,
    clock: _Clock | None = None,
    fingerprint: Callable[[], object] | None = None,
) -> EmbeddingBackfill:
    state = client.app.state

    async def refresh() -> Any:
        return embedder

    return EmbeddingBackfill(
        database=state.db,
        embedder_refresh=refresh,
        chunk_repository_factory=lambda session, user_id: ChunkRepository(session, user_id),
        quota_factory=lambda user_id: AccountQuotaService(state.db, user_id),
        cache=state.cache,
        fingerprint=fingerprint,
        interval_seconds=0,
        now=clock or _Clock(),
    )


def _set_user_columns(engine: Engine, user_id: int, **values: Any) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in values)
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE app_user SET {assignments} WHERE id = :user_id"),
            {**values, "user_id": user_id},
        )


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


def test_failure_classification_and_backoff() -> None:
    assert is_per_chunk_failure(400)
    assert is_per_chunk_failure(413)
    assert not is_per_chunk_failure(429)
    assert not is_per_chunk_failure(None)
    assert failure_code(429) == "provider_quota"
    assert failure_code(401) == "provider_auth"
    assert failure_code(None) == "provider_unreachable"
    assert failure_code(503) == "provider_unavailable"
    assert backoff_seconds(1) == 30
    assert backoff_seconds(2) == 60
    assert backoff_seconds(99) == BREAKER_MAX_SECONDS

    breaker = CircuitBreaker()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    breaker.trip("provider_quota", now)
    assert breaker.is_open(now + timedelta(seconds=29))
    assert not breaker.is_open(now + timedelta(seconds=31))
    breaker.reset()
    assert not breaker.is_open(now)


# ---------------------------------------------------------------------------
# Ingestion keeps the text and leaves vectors pending
# ---------------------------------------------------------------------------


def test_memory_written_during_a_quota_outage_is_backfilled(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def out_of_credits(self: HashingEmbedder, texts: list[str]) -> list[list[float]]:
        del self, texts
        raise EmbeddingProviderError("insufficient_quota", status_code=429)

    with monkeypatch.context() as patched:
        patched.setattr(HashingEmbedder, "embed", out_of_credits)
        create_memory(client, "The lighthouse keeper's teapot", "2026-09-05T09:00:00Z")

    states = _chunk_states(owner_engine, root_account.user_id)
    assert states and all(pending for _content, pending, _model, _f in states)
    # Keyword search finds the memory while its vector is pending.
    found = client.get("/api/v1/search", params={"query": "lighthouse teapot"})
    assert found.status_code == 200, found.text
    assert found.json()["memory_results"]

    backfill = build_embedding_backfill(client.app.state, client.app.state.db)
    embedded = client.portal.call(backfill.drain)
    assert embedded == len(states)
    after = _chunk_states(owner_engine, root_account.user_id)
    assert all(not pending and model for _content, pending, model, _f in after)


def test_durable_ingest_during_an_outage_finishes_and_is_backfilled(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def outage(self: HashingEmbedder, texts: list[str]) -> list[list[float]]:
        del self, texts
        raise EmbeddingProviderError("service unavailable", status_code=503)

    queued = client.post(
        "/api/v1/files/text/async",
        json={"path": "/outage/notes.md", "content": "Pressed violets keep their colour."},
    )
    assert queued.status_code == 202, queued.text
    job_id = int(queued.json()["id"])
    worker = client.app.state.ingest_worker
    with monkeypatch.context() as patched:
        patched.setattr(HashingEmbedder, "embed", outage)
        assert client.portal.call(worker.run_once) is True

    job = client.get(f"/api/v1/files/ingest-jobs/{job_id}").json()
    assert job["status"] == "ready", job
    states = _chunk_states(owner_engine, root_account.user_id)
    assert states and all(pending for _content, pending, _model, _f in states)

    backfill = build_embedding_backfill(client.app.state, client.app.state.db)
    assert client.portal.call(backfill.drain) == len(states)
    assert all(
        not pending for _c, pending, _m, _f in _chunk_states(owner_engine, root_account.user_id)
    )


# ---------------------------------------------------------------------------
# Backfill behaviour
# ---------------------------------------------------------------------------


def test_breaker_pauses_on_quota_and_resumes_after_recharge(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["alpha", "beta", "gamma"])
    embedder = _FakeEmbedder()
    embedder.error = 429
    clock = _Clock()
    backfill = _backfill(client, embedder, clock=clock)

    first = client.portal.call(backfill.run_once)
    assert first.breaker_open is False
    assert first.embedded == 0
    assert backfill.breaker.is_open(clock())
    calls_after_trip = len(embedder.calls)

    # While the breaker is open nothing is sent to the provider.
    paused = client.portal.call(backfill.run_once)
    assert paused.breaker_open is True
    assert len(embedder.calls) == calls_after_trip
    # Systemic failures never count against the chunks.
    assert all(
        failures == 0 for *_rest, failures in _chunk_states(owner_engine, root_account.user_id)
    )

    # Credits come back; after the backoff the loop resumes by itself.
    embedder.error = None
    clock.advance(31)
    resumed = client.portal.call(backfill.run_once)
    assert resumed.embedded == 3
    assert not backfill.breaker.is_open(clock())
    assert all(
        not pending for _c, pending, _m, _f in _chunk_states(owner_engine, root_account.user_id)
    )


def test_root_retry_nudge_and_provider_change_close_the_breaker(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["one", "two"])
    embedder = _FakeEmbedder()
    embedder.error = 402
    clock = _Clock()
    fingerprint = ["provider-a"]
    backfill = _backfill(client, embedder, clock=clock, fingerprint=lambda: fingerprint[0])
    client.portal.call(backfill.run_once)
    assert backfill.breaker.is_open(clock())

    # Root presses "retry now"; the nudge travels through the cache.
    embedder.error = None
    response = client.post("/api/v1/system/embedding-backfill/retry")
    assert response.status_code == 200, response.text
    resumed = client.portal.call(backfill.run_once)
    assert resumed.embedded == 2

    # A provider configuration change also closes an open breaker.
    _insert_pending(owner_engine, root_account.user_id, ["three"])
    embedder.error = 401
    client.portal.call(backfill.run_once)
    assert backfill.breaker.is_open(clock())
    embedder.error = None
    fingerprint[0] = "provider-b"
    assert client.portal.call(backfill.run_once).embedded == 1


def test_poison_chunk_is_isolated_and_eventually_abandoned(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["fine text", "POISON text", "more text"])
    embedder = _FakeEmbedder()
    embedder.poison_marker = "POISON"
    backfill = _backfill(client, embedder)

    first = client.portal.call(backfill.run_once)
    assert first.embedded == 2
    assert first.failed_chunks == 1
    assert not backfill.breaker.is_open(datetime.now(UTC))
    for _cycle in range(MAX_EMBEDDING_FAILURES):
        client.portal.call(backfill.run_once)
    states = {
        content: (pending, failures)
        for content, pending, _m, failures in _chunk_states(owner_engine, root_account.user_id)
    }
    assert states["fine text"] == (False, 0)
    assert states["POISON text"] == (True, MAX_EMBEDDING_FAILURES)
    status = client.get("/api/v1/system/embedding-backfill").json()
    assert status["pending_chunks"] == 0
    assert status["abandoned_chunks"] == 1


def test_spent_allowance_skips_the_account_until_raised(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["needs a vector"])
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_granted=0,
        embedding_characters=0,
        embedding_used_before_reset=0,
    )
    embedder = _FakeEmbedder()
    backfill = _backfill(client, embedder)
    blocked = client.portal.call(backfill.run_once)
    assert blocked.skipped_owners == [root_account.user_id]
    assert embedder.calls == []
    assert not backfill.breaker.is_open(datetime.now(UTC))

    _set_user_columns(owner_engine, root_account.user_id, embedding_granted=None)
    allowed = client.portal.call(backfill.run_once)
    assert allowed.embedded == 1


def test_backfill_is_idempotent_and_isolated_per_account(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
    user_client_factory: Callable[..., UserClient],
) -> None:
    member = user_client_factory()
    _insert_pending(owner_engine, root_account.user_id, ["root a", "root b"])
    _insert_pending(owner_engine, member.user_id, ["member a"], kind="history")
    embedder = _FakeEmbedder()
    backfill = _backfill(client, embedder)

    status = client.get("/api/v1/system/embedding-backfill").json()
    assert status["pending_chunks"] == 3
    assert status["pending_accounts"] == 2

    assert client.portal.call(backfill.drain) == 3
    assert client.portal.call(backfill.drain) == 0
    assert embedder.embedded_texts == 3  # Nothing is embedded twice.
    assert all(not p for _c, p, _m, _f in _chunk_states(owner_engine, member.user_id))

    # The status view is root-only.
    denied = member.client.get("/api/v1/system/embedding-backfill")
    assert denied.status_code == 403
    denied_retry = member.client.post("/api/v1/system/embedding-backfill/retry")
    assert denied_retry.status_code == 403


def test_disabled_embeddings_leave_rows_untouched(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["kept as text"])
    embedder = _FakeEmbedder()
    embedder.dimension = 0  # type: ignore[misc]
    backfill = _backfill(client, embedder)
    batch = client.portal.call(backfill.run_once)
    assert batch.disabled is True
    assert embedder.calls == []
    status = client.get("/api/v1/system/embedding-backfill").json()
    assert status["worker_state"] == "disabled"
    assert status["pending_chunks"] == 1


def test_status_service_reports_paused_worker(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _insert_pending(owner_engine, root_account.user_id, ["waiting"])
    embedder = _FakeEmbedder()
    embedder.error = 429
    clock = _Clock()
    backfill = _backfill(client, embedder, clock=clock)
    client.portal.call(backfill.run_once)
    client.portal.call(backfill.run_once)  # publishes the paused state
    service = EmbeddingBackfillStatusService(client.app.state.db, client.app.state.cache)
    status = client.portal.call(service.status)
    assert status.worker_state == "paused"
    assert status.last_error_code == "provider_quota"
    assert status.resume_at is not None
    assert status.pending_chunks == 1
