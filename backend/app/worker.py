"""Dedicated durable-ingestion worker process.

Run ``python -m app.worker`` (or ``apsor-archive worker`` / ``make worker``) as
its own service; this is the supported way to drain ingestion. The API only
enqueues jobs and publishes wake-ups unless ``APSOR_INGEST_WORKER_ENABLED=true``
opts it into a single-process development mode. Both modes share the same
PostgreSQL job queue and lease, so either can drain a queue left by the other.

The loop polls immediately, processes every claimable job without sleeping,
and waits ``APSOR_INGEST_POLL_SECONDS`` (one second by default) only when the
queue is empty. The same process also sweeps expired unsent chat images using
the database-backed ``agent_config`` lifetime and interval, refreshed each
cycle. SIGINT/SIGTERM stop both loops gracefully.

At most ``APSOR_INGEST_MAX_IN_FLIGHT_JOBS`` jobs run concurrently, and their
parsing/chunking work is capped by a shared ``ThreadPoolExecutor`` sized by
``APSOR_INGEST_EXTRACT_WORKERS`` (two by default). Embedding has a separate
shared async semaphore ``APSOR_INGEST_EMBEDDING_CONCURRENCY`` (six by
default). Pure-Python CPU-bound work can later move to a process pool; the job,
lease, and progress contracts do not depend on the executor type.
"""

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence

from starlette.datastructures import State

from app.bootstrap import build_background_services, close_process_state, open_process_state
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.migrations import upgrade_to_head
from app.infrastructure.logger.logging import configure_logging

logger = logging.getLogger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Stop the polling loop cleanly when the container is asked to exit."""
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows event loops and some test harnesses do not support this.
            logger.debug("Signal handler for %s is unavailable", signum)


async def run_worker(settings: Settings, *, once: bool = False) -> None:
    """Own the worker's database, cache, storage, and AI runtime resources."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.run_migrations:
        await asyncio.to_thread(upgrade_to_head, settings.database_url)
    # Alembic's alembic.ini logging config resets the root logger to WARNING.
    # Configure application logging after the migration so worker job logs
    # remain visible.
    configure_logging(debug=settings.debug)

    state = State()
    try:
        await open_process_state(state, settings)
        services = await build_background_services(state, settings)
        try:
            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            if once:
                removed = await services.cleanup.run_once()
                history_batch = await services.history_indexer.run_once()
                processed = await services.worker.run_once()
                logger.info(
                    "Worker --once finished; processed=%s attachments_removed=%s "
                    "history_examined=%s history_indexed=%s",
                    processed,
                    removed,
                    history_batch.examined,
                    history_batch.indexed,
                )
            else:
                services.start_side_loops(settings, stop_event)
                await services.worker.run_forever(stop_event)
        finally:
            await services.stop()
    finally:
        await close_process_state(state)


def main(argv: Sequence[str] | None = None) -> None:
    """Parse CLI flags and run the worker until it is stopped."""
    parser = argparse.ArgumentParser(description="Run the Apsor Archive ingestion worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued job, then exit.",
    )
    arguments = parser.parse_args(argv)
    try:
        asyncio.run(run_worker(get_settings(), once=arguments.once))
    except KeyboardInterrupt:
        logger.info("Ingestion worker interrupted")


if __name__ == "__main__":
    main()
