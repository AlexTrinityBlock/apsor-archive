"""Granular ingestion progress: tracker, extraction hooks, pub/sub, and SSE."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.dependency.auth import (
    require_authenticated,
    require_stateless_authenticated,
)
from app.infrastructure.cache.progress_bus import (
    CHANNEL_PREFIX,
    ValkeyProgressBus,
    build_progress_bus,
    progress_channel,
)
from app.infrastructure.database.session import get_db_session
from app.module.knowledge.domain.chunking_domain import chunk_text
from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.domain.ingest_progress_domain import (
    PHASE_CHUNKING,
    PHASE_IDLE,
    PHASE_PARSING,
    ProgressTracker,
)
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    render_vision_prompt,
)
from app.module.knowledge.protocol.progress_bus_protocol import (
    NullProgressBus,
    ProgressBusUnavailable,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument
from app.module.knowledge.schema.file_schema import (
    IngestJobSchema,
    IngestProgressEventSchema,
)
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.ingest_job_service import IngestWorker, _JobProgress
from app.module.knowledge.service.ingest_progress_service import IngestProgressService
from app.shared.time import utcnow


class _FakeVisionExtractor:
    """Return one deterministic document per rendered page."""

    configured = True
    model_name = "fake-vision"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: str = "image",
    ) -> VisionDocument:
        del data, mime_type, system_prompt, mode
        self.calls += 1
        return VisionDocument(
            text=f"page {self.calls}",
            caption="page",
            ocr_text=f"page {self.calls}",
            title="page",
            summary="page",
            document_type="scanned_pdf",
            tags=["page"],
            language="en",
            description="A scanned page.",
        )


class _FakeProgressBus:
    """Deterministic bus with optional subscription failure and blocking tail."""

    def __init__(
        self,
        events: tuple[IngestProgressEventSchema, ...] = (),
        *,
        block: bool = False,
    ) -> None:
        self.events = events
        self.block = block
        self.published: list[IngestProgressEventSchema] = []
        self.closed = False

    async def publish(self, event: IngestProgressEventSchema) -> None:
        self.published.append(event)

    @asynccontextmanager
    async def subscribe(
        self,
        job_id: int,
    ) -> AsyncIterator[AsyncIterator[IngestProgressEventSchema]]:
        del job_id

        async def events() -> AsyncIterator[IngestProgressEventSchema]:
            for event in self.events:
                yield event
            if self.block:
                await asyncio.Event().wait()

        yield events()

    async def close(self) -> None:
        self.closed = True


class _FakePubSub:
    """Minimal redis.asyncio PubSub surface used by the adapter."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.channel: str | None = None
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.channel = channel

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        for payload in self.messages:
            yield {"type": "message", "data": payload}

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    """Minimal redis.asyncio client surface used by the adapter."""

    def __init__(self, messages: list[str] | None = None) -> None:
        self.published: list[tuple[str, str]] = []
        self.pubsub_client = _FakePubSub(list(messages or []))
        self.closed = False

    async def publish(self, channel: str, data: str) -> None:
        self.published.append((channel, data))

    def pubsub(self) -> _FakePubSub:
        return self.pubsub_client

    async def aclose(self) -> None:
        self.closed = True


def _frame_payloads(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse the SSE frames in a fully buffered stream body."""
    frames: list[tuple[str, dict[str, Any]]] = []
    for raw in body.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in raw.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if data_lines:
            payload: dict[str, Any] = json.loads("\n".join(data_lines))
            frames.append((event_name, payload))
    return frames


def _event_from_job(
    job: IngestJobSchema,
    **overrides: Any,
) -> IngestProgressEventSchema:
    base = IngestProgressEventSchema.model_validate(job)
    return IngestProgressEventSchema.model_validate(
        {**base.model_dump(), **overrides}
    )


def test_progress_tracker_versions_and_clamping() -> None:
    tracker = ProgressTracker()
    idle = tracker.snapshot()
    assert idle.phase == PHASE_IDLE
    assert idle.version == 0

    started = tracker.begin(PHASE_PARSING, 3, "page")
    assert started.done == 0
    assert started.total == 3
    assert started.unit == "page"
    assert started.version == 1

    tracker.advance()
    tracker.advance_to(99)
    snapshot = tracker.snapshot()
    assert snapshot.done == 3
    assert snapshot.version == 3

    finished = tracker.finish()
    assert finished.phase == PHASE_IDLE
    assert finished.total is None
    assert finished.unit is None
    assert finished.version == 4

    with pytest.raises(ValueError):
        tracker.begin("parsing", -1, "page")
    with pytest.raises(ValueError):
        tracker.begin("parsing", 1, "word")


def test_chunk_text_reports_each_draft() -> None:
    calls: list[tuple[int, int]] = []
    text_value = " ".join(f"Sentence number {index} about bearings." for index in range(80))

    drafts = chunk_text(
        text_value,
        target_chars=200,
        overlap_chars=20,
        on_progress=lambda done, total: calls.append((done, total)),
    )

    assert drafts
    total = calls[0][1]
    assert total > 0
    assert calls[0] == (0, total)
    assert calls[-1] == (len(drafts), total)
    assert all(done <= total for done, _total in calls)
    assert [done for done, _total in calls] == sorted(done for done, _total in calls)


def test_pdf_text_reports_one_page_per_advance(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Page:
        def __init__(self, value: str) -> None:
            self.value = value

        def extract_text(self) -> str:
            return self.value

    class _Reader:
        def __init__(self, _stream: object) -> None:
            self.pages = [_Page("first"), _Page("second"), _Page("third")]

    monkeypatch.setattr(
        "app.module.knowledge.service.file_service.PdfReader",
        _Reader,
    )
    tracker = ProgressTracker()

    text_value = FileService._pdf_text(b"ignored", tracker)

    assert text_value == "first\n\nsecond\n\nthird"
    snapshot = tracker.snapshot()
    assert snapshot.phase == PHASE_PARSING
    assert snapshot.done == 3
    assert snapshot.total == 3
    assert snapshot.unit == "page"


def test_pdf_vision_reports_after_each_page(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = ProgressTracker()
    service = object.__new__(FileService)
    service.progress_tracker = tracker
    service.vision_max_pages = 4
    service.vision_extractor = _FakeVisionExtractor()
    service.chat_quota = None
    service.cpu_runner = asyncio.to_thread
    service._vision_prompts = {
        "document": render_vision_prompt(
            DEFAULT_VISION_DOCUMENT_PROMPT,
            "en",
            mode="document",
        )
    }
    monkeypatch.setattr(
        FileService,
        "_render_pdf_pages",
        staticmethod(lambda _data, _max_pages: [b"one", b"two"]),
    )

    async def scenario() -> str:
        text_value, _summary, _tags, _doc_type, _prompt = await service._vision_pdf(
            b"pdf"
        )
        return text_value

    assert asyncio.run(scenario()).startswith("## Visible text")
    snapshot = tracker.snapshot()
    assert snapshot.phase == PHASE_PARSING
    assert snapshot.done == 2
    assert snapshot.total == 2
    assert snapshot.unit == "page"


def _stub_worker(progress_bus: Any = None) -> IngestWorker:
    return IngestWorker(
        session_factory=None,
        file_service_factory=None,
        storage=None,
        max_attempts=1,
        runtime_config=IngestRuntimeConfig(),
        progress_bus=progress_bus,
    )


def test_job_progress_reports_parsing_and_chunking_percentages() -> None:
    worker = _stub_worker()
    writes: list[dict[str, Any]] = []

    async def fake_update(
        _job_id: int,
        _user_id: int,
        **fields: Any,
    ) -> None:
        writes.append(fields)

    worker.update_job = fake_update  # type: ignore[method-assign]
    tracker = ProgressTracker()
    progress = _JobProgress(worker, 7, 11, tracker)

    tracker.begin(PHASE_PARSING, 10, "page")
    tracker.advance_to(4)
    asyncio.run(progress.report())
    assert writes[-1]["status"] == "parsing"
    assert writes[-1]["progress_pct"] == 5 + int(40 * 4 / 10)
    assert writes[-1]["stage"] == "Extracting 4/10 page"
    assert writes[-1]["stage_done"] == 4
    assert writes[-1]["stage_total"] == 10
    assert writes[-1]["stage_unit"] == "page"

    tracker.begin(PHASE_CHUNKING, 20, "chunk")
    tracker.advance_to(8)
    asyncio.run(progress.report())
    assert writes[-1]["status"] == "chunking"
    assert writes[-1]["progress_pct"] == 45 + int(15 * 8 / 20)
    assert writes[-1]["stage"] == "Chunking 8/20 chunks"
    assert writes[-1]["stage_unit"] == "chunk"

    tracker.finish()
    asyncio.run(progress.report())
    assert writes[-1] == {}


def test_job_progress_milestones_clear_stage_fields() -> None:
    worker = _stub_worker()
    writes: list[dict[str, Any]] = []

    async def fake_update(
        _job_id: int,
        _user_id: int,
        **fields: Any,
    ) -> None:
        writes.append(fields)

    worker.update_job = fake_update  # type: ignore[method-assign]
    tracker = ProgressTracker()
    progress = _JobProgress(worker, 7, 11, tracker, None)

    asyncio.run(progress.chunked(20))
    assert writes[-1]["progress_pct"] == 60
    assert writes[-1]["chunks_total"] == 20
    assert writes[-1]["stage_done"] is None
    assert tracker.snapshot().phase == PHASE_IDLE

    asyncio.run(progress.embedded(10, 20))
    assert writes[-1]["status"] == "embedding"
    assert writes[-1]["progress_pct"] == 60 + int(32 * 10 / 20)
    assert writes[-1]["chunks_embedded"] == 10


def test_worker_publishes_after_committed_update(
    client: TestClient,
    root_account: Any,
) -> None:
    job = client.post(
        "/api/v1/files/text/async",
        json={"path": "/progress/publish.md", "content": "Progress publish test."},
    ).json()
    worker = client.app.state.ingest_worker
    bus = _FakeProgressBus()
    original_bus = worker.progress_bus
    worker.progress_bus = bus

    async def scenario() -> IngestJobSchema | None:
        return await worker.update_job(
            job["id"],
            root_account.user_id,
            status="parsing",
            stage_done=2,
            stage_total=5,
            stage_unit="page",
        )

    try:
        assert client.portal is not None
        schema = client.portal.call(scenario)
    finally:
        worker.progress_bus = original_bus

    assert schema is not None
    assert schema.stage_done == 2
    assert len(bus.published) == 1
    assert bus.published[0].id == job["id"]
    assert bus.published[0].stage_total == 5


def test_progress_bus_adapter_publishes_and_subscribes() -> None:
    event = IngestProgressEventSchema(
        id=7,
        status="parsing",
        stage="Extracting 2/5 page",
        progress_pct=21,
        stage_done=2,
        stage_total=5,
        stage_unit="page",
        chunks_total=None,
        chunks_embedded=None,
        file_id=None,
        error_code=None,
        error_detail=None,
        updated_at=datetime.now(UTC),
    )
    fake = _FakeRedis([event.model_dump_json(), "not-json", event.model_dump_json()])
    bus = object.__new__(ValkeyProgressBus)
    bus._client = fake

    async def scenario() -> list[IngestProgressEventSchema]:
        await bus.publish(event)
        received: list[IngestProgressEventSchema] = []
        async with bus.subscribe(7) as events:
            async for item in events:
                received.append(item)
        await bus.close()
        return received

    received = asyncio.run(scenario())

    assert fake.published[0][0] == f"{CHANNEL_PREFIX}7"
    assert json.loads(fake.published[0][1])["stage_done"] == 2
    assert [item.stage_done for item in received] == [2, 2]
    assert fake.pubsub_client.channel == progress_channel(7)
    assert fake.pubsub_client.closed is True
    assert fake.closed is True


def test_build_progress_bus_returns_null_for_memory() -> None:
    for url in ("", "memory://", "none"):
        bus = build_progress_bus(url)
        assert isinstance(bus, NullProgressBus)
        with pytest.raises(ProgressBusUnavailable):
            bus.subscribe(1)


def _create_queued_job(client: TestClient, path: str) -> IngestJobSchema:
    response = client.post(
        "/api/v1/files/text/async",
        json={"path": path, "content": "Progress service fixture content."},
    )
    assert response.status_code == 202, response.text
    return IngestJobSchema.model_validate(response.json())


def _progress_service(
    client: TestClient,
    *,
    bus: Any,
    user_id: int,
    keepalive_seconds: float = 15.0,
    poll_seconds: float = 1.0,
) -> IngestProgressService:
    return IngestProgressService(
        database=client.app.state.db,
        progress_bus=bus,
        user_id=user_id,
        role="root",
        keepalive_seconds=keepalive_seconds,
        poll_seconds=poll_seconds,
    )


def test_progress_service_streams_newer_events_and_closes_on_terminal(
    client: TestClient,
    root_account: Any,
) -> None:
    job = _create_queued_job(client, "/progress/stream.md")
    current = IngestProgressEventSchema.model_validate(job)
    parsing = _event_from_job(
        job,
        status="parsing",
        stage="Extracting 4/10 page",
        progress_pct=21,
        stage_done=4,
        stage_total=10,
        stage_unit="page",
        updated_at=current.updated_at + timedelta(seconds=1),
    )
    stale = _event_from_job(
        job,
        status="parsing",
        stage="Extracting 1/10 page",
        updated_at=current.updated_at - timedelta(seconds=1),
    )
    ready = _event_from_job(
        job,
        status="ready",
        stage="Ready",
        progress_pct=100,
        stage_done=None,
        stage_total=None,
        stage_unit=None,
        updated_at=current.updated_at + timedelta(seconds=2),
    )
    bus = _FakeProgressBus((parsing, stale, ready))
    service = _progress_service(client, bus=bus, user_id=root_account.user_id)

    async def scenario() -> list[str]:
        return [frame async for frame in service.stream(job.id)]

    frames = client.portal.call(scenario) if client.portal is not None else []
    parsed = _frame_payloads("".join(frames))

    assert [name for name, _payload in parsed] == ["snapshot", "progress", "progress"]
    assert parsed[1][1]["stage"] == "Extracting 4/10 page"
    assert parsed[2][1]["status"] == "ready"
    assert parsed[0][1]["id"] == job.id
    assert "path" not in parsed[0][1]


def test_progress_service_sends_keepalives(client: TestClient, root_account: Any) -> None:
    job = _create_queued_job(client, "/progress/keepalive.md")
    bus = _FakeProgressBus(block=True)
    service = _progress_service(
        client,
        bus=bus,
        user_id=root_account.user_id,
        keepalive_seconds=0.01,
    )

    async def scenario() -> list[str]:
        stream = service.stream(job.id)
        frames: list[str] = []
        try:
            frames.append(await anext(stream))
            frames.append(await anext(stream))
            frames.append(await anext(stream))
        finally:
            await stream.aclose()
        return frames

    frames = client.portal.call(scenario) if client.portal is not None else []

    assert frames[0].startswith("event: snapshot")
    assert frames[1] == ": keepalive\n\n"
    assert frames[2] == ": keepalive\n\n"


def test_progress_service_polls_when_subscription_is_unavailable(
    client: TestClient,
    root_account: Any,
) -> None:
    job = _create_queued_job(client, "/progress/fallback.md")
    bus = NullProgressBus()
    service = _progress_service(
        client,
        bus=bus,
        user_id=root_account.user_id,
        poll_seconds=0.01,
    )
    worker = client.app.state.ingest_worker

    async def scenario() -> list[str]:
        async def finish_soon() -> None:
            await asyncio.sleep(0.03)
            await worker.update_job(
                job.id,
                root_account.user_id,
                status="ready",
                stage="Ready",
                progress_pct=100,
                finished_at=utcnow(),
            )

        finisher = asyncio.create_task(finish_soon())
        frames: list[str] = []
        try:
            async with asyncio.timeout(2):
                async for frame in service.stream(job.id):
                    frames.append(frame)
        finally:
            await finisher
        return frames

    frames = client.portal.call(scenario) if client.portal is not None else []
    parsed = _frame_payloads("".join(frames))

    assert parsed[0][0] == "snapshot"
    assert parsed[-1][0] == "progress"
    assert parsed[-1][1]["status"] == "ready"
    assert parsed[-1][1]["progress_pct"] == 100


def test_sse_route_streams_snapshot_for_ready_job(
    client: TestClient,
) -> None:
    job = _create_queued_job(client, "/progress/route.md")
    assert client.portal is not None
    client.portal.call(client.app.state.ingest_worker.process_job, job.id)

    with client.stream(
        "GET",
        f"/api/v1/files/ingest-jobs/{job.id}/events",
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache, no-transform"
        assert response.headers["x-accel-buffering"] == "no"
        body = "".join(response.iter_text())

    parsed = _frame_payloads(body)
    assert parsed[0][0] == "snapshot"
    assert parsed[0][1]["status"] == "ready"
    assert parsed[0][1]["progress_pct"] == 100


def test_sse_route_requires_auth_and_owner(
    client: TestClient,
    client_factory: Any,
    user_client_factory: Any,
    root_account: Any,
) -> None:
    job = _create_queued_job(client, "/progress/owner.md")
    assert client.portal is not None
    client.portal.call(client.app.state.ingest_worker.process_job, job.id)
    member = user_client_factory("progress.member")
    anonymous = client_factory()

    anonymous_response = anonymous.get(
        f"/api/v1/files/ingest-jobs/{job.id}/events",
    )
    assert anonymous_response.status_code == 401

    foreign = member.client.get(
        f"/api/v1/files/ingest-jobs/{job.id}/events",
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"] == "ingest_job_not_found"


def test_sse_route_uses_stateless_auth_without_request_session(
    client: TestClient,
) -> None:
    path = "/files/ingest-jobs/{job_id}/events"

    def iter_routes(routes: Any) -> Any:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from iter_routes(inner.routes)
            elif hasattr(route, "dependant"):
                yield route

    route = next(
        route
        for route in iter_routes(client.app.routes)
        if getattr(route, "path", None) == path
    )

    def collect_calls(dependant: Any) -> set[Any]:
        calls = {dependant.call}
        for child in dependant.dependencies:
            calls.update(collect_calls(child))
        return calls

    calls = collect_calls(route.dependant)
    assert require_stateless_authenticated in calls
    assert require_authenticated not in calls
    assert get_db_session not in calls


def test_ingest_job_api_exposes_and_constrains_stage_progress(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    job = _create_queued_job(client, "/progress/constraints.md")
    body = client.get(f"/api/v1/files/ingest-jobs/{job.id}").json()
    assert body["stage_done"] is None
    assert body["stage_total"] is None
    assert body["stage_unit"] is None

    with pytest.raises(IntegrityError):
        with owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE file_ingest_job "
                    "SET stage_done = 5, stage_total = 4, stage_unit = 'page' "
                    "WHERE id = :job_id"
                ),
                {"job_id": job.id},
            )

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file_ingest_job "
                "SET stage_done = 2, stage_total = 5, stage_unit = 'page' "
                "WHERE id = :job_id"
            ),
            {"job_id": job.id},
        )
    allowed = client.get(f"/api/v1/files/ingest-jobs/{job.id}").json()
    assert allowed["stage_done"] == 2
    assert allowed["stage_total"] == 5
    assert allowed["stage_unit"] == "page"
