"""Process wiring for the dedicated worker and the opt-in in-API dev mode."""

import asyncio

from fastapi.testclient import TestClient

from app.infrastructure.config.settings import Settings
from app.main import create_app
from app.worker import run_worker


def test_ingest_worker_is_opt_in_by_default() -> None:
    """The API never drains ingestion unless the dev mode is requested."""
    assert Settings(_env_file=None).ingest_worker_enabled is False


def test_api_without_worker_mode_builds_no_worker(settings: Settings) -> None:
    """With the default flag the lifespan creates no worker or consumer."""
    with TestClient(create_app(settings)) as client:
        state = client.app.state
        assert getattr(state, "ingest_worker", None) is None
        assert getattr(state, "job_consumer", None) is None
        assert client.get("/api/v1/health").status_code == 200


def test_api_dev_mode_runs_and_stops_the_worker_loops(settings: Settings) -> None:
    """The opt-in mode starts the shared background loops and shuts them down."""
    dev_settings = settings.model_copy(update={"ingest_worker_enabled": True})
    with TestClient(create_app(dev_settings)) as client:
        worker = client.app.state.ingest_worker
        assert worker is not None
        assert client.portal.call(worker.run_once) is False


def test_worker_once_drains_an_empty_queue(settings: Settings) -> None:
    """``apsor-archive worker --once`` opens and releases its own resources."""
    asyncio.run(run_worker(settings, once=True))
