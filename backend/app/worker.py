"""Dedicated durable-ingestion worker process.

Run ``python -m app.worker`` (or ``apsor-archive worker``) as its own service
when the API should stay responsive under long uploads. The worker uses the
same PostgreSQL job queue and lease as the lifespan fallback, so either mode
can drain a queue left by the other.

The loop polls immediately, processes every claimable job without sleeping,
and waits ``APSOR_INGEST_POLL_SECONDS`` (one second by default) only when the
queue is empty. SIGINT/SIGTERM stop the loop gracefully.

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

from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.cache.resilient_cache import build_cache
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.migrations import upgrade_to_head
from app.infrastructure.database.session import Database
from app.infrastructure.files.local_storage import LocalFileStorage
from app.infrastructure.logger.logging import configure_logging
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.knowledge.dependencies import (
    build_ingest_worker,
    ingest_runtime_defaults,
    load_ingest_runtime_config,
)
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)

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
    configure_logging(debug=settings.debug)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.run_migrations:
        await asyncio.to_thread(upgrade_to_head, settings.database_url)

    database = Database(settings.database_url, echo=settings.debug)
    cache = build_cache(settings.cache_url)
    storage = LocalFileStorage(settings.data_dir)
    cipher = SecretCipher.from_settings(settings)
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cipher,
        defaults=provider_defaults_from_settings(settings),
    )
    try:
        async with database.session_factory() as session:
            await runtime.reload(ProviderConfigRepository(session))

        state = State()
        state.settings = settings
        state.db = database
        state.cache = cache
        state.storage = storage
        state.secret_cipher = cipher
        state.ai_runtime = runtime

        ingest_defaults = ingest_runtime_defaults(settings)
        ingest_config = await load_ingest_runtime_config(
            database.session_factory,
            ingest_defaults,
        )
        worker = build_ingest_worker(
            state,
            database.session_factory,
            settings,
            runtime_config=ingest_config,
            config_provider=lambda: load_ingest_runtime_config(
                database.session_factory,
                ingest_defaults,
            ),
        )
        try:
            await worker.startup()

            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            if once:
                processed = await worker.run_once()
                logger.info("Worker --once finished; processed=%s", processed)
            else:
                await worker.run_forever(stop_event)
        finally:
            worker.close()
    finally:
        await cache.close()
        await database.dispose()


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
