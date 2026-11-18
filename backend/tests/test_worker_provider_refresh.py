"""Worker provider refresh: batch boundaries, mid-job recovery, and DB pickup."""

import asyncio
import logging
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from starlette.datastructures import State

from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import system_session
from app.module.knowledge.dependencies import (
    build_ingest_worker,
    build_provider_refresh,
)
from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.exception.domain_error import EmbeddingProviderError
from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)
from app.module.knowledge.service.indexer_service import IndexerService
from app.module.knowledge.service.ingest_job_service import IngestWorker


class _FakeEmbedder:
    """A deterministic embedder that can reject its first authenticated calls."""

    def __init__(
        self,
        *,
        model_name: str = "fake-embed",
        dimension: int = 8,
        authorized: bool = True,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.authorized = authorized
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        # Yield so concurrently started batches reach the provider together;
        # this is what makes the single-refresh lock observable in the test.
        await asyncio.sleep(0)
        if not self.authorized:
            raise EmbeddingProviderError("401 Unauthorized", status_code=401)
        return [[0.05] * self.dimension for _text in texts]


class _EmptyProviderRepository:
    """No active provider rows: the runtime resolves the environment defaults."""

    async def list_active_chain(self, spec: Any) -> list[Any]:
        del spec
        return []

    async def get_active(self, spec: Any) -> None:
        del spec
        return None


class _RecordingChunkRepository:
    """Collect written chunks without a database session."""

    def __init__(self) -> None:
        self.chunks: list[ChunkModel] = []

    async def add(self, chunk: ChunkModel) -> ChunkModel:
        self.chunks.append(chunk)
        return chunk

    async def add_ngrams(self, chunk_id: int, frequencies: dict[str, int]) -> None:
        del chunk_id, frequencies


def _drafts(count: int) -> list[ChunkDraft]:
    return [
        ChunkDraft(
            index=index + 1,
            content=f"chunk number {index}",
            char_count=15,
            token_count=3,
        )
        for index in range(count)
    ]


def test_indexer_refreshes_once_after_401_and_keeps_the_same_model() -> None:
    """One concurrent batch failure triggers one refresh and a clean retry."""

    async def scenario() -> None:
        repository = _RecordingChunkRepository()
        stale = _FakeEmbedder(authorized=False)
        recovered = _FakeEmbedder()
        refreshes = 0

        async def refresh() -> EmbedderProtocol:
            nonlocal refreshes
            refreshes += 1
            return recovered

        indexer = IndexerService(
            repository,
            stale,
            user_id=1,
            embedding_batch_size=2,
            embedding_retry_seconds=0,
            fail_on_embedding_error=True,
            embedding_refresh=refresh,
        )

        total = await indexer.index_chunks(
            source_kind="file",
            source_id=1,
            drafts=_drafts(6),
        )

        assert total == 6
        assert stale.calls >= 2  # Several batches failed before the refresh won.
        assert refreshes == 1
        assert indexer.embedder is recovered
        assert len(repository.chunks) == 6
        assert all(chunk.embedding is not None for chunk in repository.chunks)
        assert {chunk.embedding_model for chunk in repository.chunks} == {"fake-embed"}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("model_name", "dimension"),
    [("other-embed", 8), ("fake-embed", 16)],
)
def test_indexer_rejects_a_different_model_or_dimension(
    model_name: str,
    dimension: int,
) -> None:
    """A mid-job shape change fails the job instead of mixing vectors."""

    async def scenario() -> None:
        repository = _RecordingChunkRepository()
        stale = _FakeEmbedder(authorized=False)
        changed = _FakeEmbedder(model_name=model_name, dimension=dimension)
        refreshes = 0

        async def refresh() -> EmbedderProtocol:
            nonlocal refreshes
            refreshes += 1
            return changed

        indexer = IndexerService(
            repository,
            stale,
            user_id=1,
            embedding_batch_size=3,
            embedding_retry_seconds=0,
            fail_on_embedding_error=True,
            embedding_refresh=refresh,
        )

        with pytest.raises(EmbeddingProviderError) as error:
            await indexer.index_chunks(
                source_kind="file",
                source_id=2,
                drafts=_drafts(3),
            )

        assert "changed model or dimension" in str(error.value)
        assert error.value.status_code == 401
        assert refreshes == 1
        assert indexer.embedder is stale
        assert indexer.embedder.model_name == "fake-embed"
        assert indexer.embedder.dimension == 8
        assert repository.chunks == []

    asyncio.run(scenario())


def test_routine_reload_keeps_info_quiet_until_the_snapshot_changes(
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup announces once; an unchanged routine refresh stays at DEBUG."""
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cast(Any, None),
        defaults=provider_defaults_from_settings(settings),
    )
    repository = _EmptyProviderRepository()

    async def scenario() -> None:
        with caplog.at_level(
            logging.INFO,
            logger="app.infrastructure.ai.runtime",
        ):
            # Startup and root writes announce the snapshot.
            assert await runtime.reload(repository) is False
            # The worker's batch-boundary refresh does not repeat that line.
            assert await runtime.reload(repository, announce=False) is False
            assert (
                sum("provider runtime loaded" in record.message for record in caplog.records) == 1
            )

            # A real change is still visible at INFO even on a quiet refresh.
            runtime.embedding_config = runtime.embedding_config.model_copy(
                update={"model": "changed-elsewhere"}
            )
            assert await runtime.reload(repository, announce=False) is True
            assert (
                sum("provider runtime loaded" in record.message for record in caplog.records) == 2
            )

    asyncio.run(scenario())


def _stub_worker_kwargs() -> dict[str, Any]:
    """Build the inert constructor arguments shared by the loop tests."""
    return {
        "session_factory": None,
        "file_service_factory": None,
        "storage": None,
        "max_attempts": 1,
        "runtime_config": IngestRuntimeConfig(),
    }


class _OrderRecordingWorker(IngestWorker):
    """Record whether the refresh happened before a claim."""

    def __init__(self, events: list[str]) -> None:
        super().__init__(
            **_stub_worker_kwargs(),
            provider_refresh=self._refresh,
        )
        self.events = events

    async def _refresh(self) -> EmbedderProtocol:
        self.events.append("refresh")
        return cast(EmbedderProtocol, None)

    async def _claim_next(self) -> tuple[int, int] | None:
        self.events.append("claim")
        return None


class _HoldingWorker(IngestWorker):
    """Claim one job, hold it in flight, and count refresh calls."""

    def __init__(self, events: list[str]) -> None:
        super().__init__(
            **_stub_worker_kwargs(),
            provider_refresh=self._refresh,
        )
        self.events = events
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.claims = 0

    async def _refresh(self) -> EmbedderProtocol:
        self.events.append("refresh")
        return cast(EmbedderProtocol, None)

    async def _claim_next(self) -> tuple[int, int] | None:
        self.events.append("claim")
        if self.claims:
            return None
        self.claims += 1
        return (1, 1)

    async def _process_claimed(
        self,
        job_id: int,
        user_id: int,
        runtime: Any,
    ) -> None:
        self.started.set()
        await self.release.wait()


def test_run_once_refreshes_before_claiming() -> None:
    """A single-job pass reloads the provider snapshot before it claims."""

    async def scenario() -> None:
        events: list[str] = []
        worker = _OrderRecordingWorker(events)

        assert await worker.run_once() is False
        assert events == ["refresh", "claim"]

    asyncio.run(scenario())


def test_run_forever_does_not_refresh_while_a_job_is_in_flight() -> None:
    """Routine refresh waits for the whole batch to drain."""

    async def scenario() -> None:
        events: list[str] = []
        worker = _HoldingWorker(events)
        worker.poll_seconds = 0.25
        stop_event = asyncio.Event()
        loop_task = asyncio.create_task(worker.run_forever(stop_event))

        await asyncio.wait_for(worker.started.wait(), timeout=1)
        await asyncio.sleep(0.3)
        assert events.count("refresh") == 1

        worker.release.set()
        for _attempt in range(100):
            if events.count("refresh") >= 2:
                break
            await asyncio.sleep(0.01)
        stop_event.set()
        await asyncio.wait_for(loop_task, timeout=1)

        assert events.count("refresh") == 2

    asyncio.run(scenario())


def _build_dedicated_runtime(client: TestClient) -> AiRuntime:
    """Build a runtime that belongs only to the test worker, not to the API."""

    settings = client.app.state.settings
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=client.app.state.secret_cipher,
        defaults=provider_defaults_from_settings(settings),
    )

    async def load() -> None:
        async with system_session(client.app.state.db.session_factory) as session:
            await runtime.reload(ProviderConfigRepository(session))

    assert client.portal is not None
    client.portal.call(load)
    return runtime


def _chunk_shapes(engine: Engine, file_id: int) -> set[tuple[str | None, int | None]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT DISTINCT embedding_model, jsonb_array_length(embedding) "
                "FROM chunk WHERE source_kind = 'file' AND source_id = :file_id"
            ),
            {"file_id": file_id},
        ).all()
    return {(row[0], row[1]) for row in rows}


def _enqueue_text_job(client: TestClient, path: str) -> int:
    response = client.post(
        "/api/v1/files/text/async",
        json={"path": path, "content": "Batch boundary notes for the worker. " * 30},
    )
    assert response.status_code == 202, response.text
    return int(response.json()["id"])


def test_worker_picks_up_a_provider_change_on_the_next_run_once(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A separate worker runtime reloads the database snapshot between jobs."""

    settings = client.app.state.settings
    runtime = _build_dedicated_runtime(client)
    assert runtime.embedding_config.model == settings.embedding_model
    assert runtime.embedding_config.dimension == settings.embedding_dimension

    state = State()
    state.settings = settings
    state.cache = client.app.state.cache
    state.storage = client.app.state.storage
    state.secret_cipher = client.app.state.secret_cipher
    state.ai_runtime = runtime
    worker = build_ingest_worker(
        state,
        client.app.state.db.session_factory,
        settings,
        provider_refresh=build_provider_refresh(
            runtime,
            client.app.state.db.session_factory,
        ),
    )
    try:
        first_job = _enqueue_text_job(client, "/providers/first.md")
        assert client.portal.call(worker.run_once) is True
        first_state = client.get(f"/api/v1/files/ingest-jobs/{first_job}").json()
        assert first_state["status"] == "ready"
        assert _chunk_shapes(owner_engine, int(first_state["file_id"])) == {
            (settings.embedding_model, settings.embedding_dimension)
        }

        # The API write reloads only the API runtime. This worker keeps its old
        # snapshot until its next batch boundary.
        changed = client.post(
            "/api/v1/settings/providers/embedding",
            json={
                "provider": "hashing",
                "label": "Small hashing",
                "model": "apsor-hash-32",
                "dimension": 32,
            },
        )
        assert changed.status_code == 200, changed.text
        assert runtime.embedding_config.model == settings.embedding_model

        second_job = _enqueue_text_job(client, "/providers/second.md")
        assert client.portal.call(worker.run_once) is True
        assert runtime.embedding_config.model == "apsor-hash-32"
        assert runtime.embedding_config.dimension == 32
        second_state = client.get(f"/api/v1/files/ingest-jobs/{second_job}").json()
        assert second_state["status"] == "ready"
        assert _chunk_shapes(owner_engine, int(second_state["file_id"])) == {
            ("apsor-hash-32", 32)
        }
    finally:
        worker.close()
