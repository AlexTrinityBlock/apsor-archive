"""Process bootstrap shared by the API lifespan and the ingestion worker.

Both entrypoints need the same process-wide resources (database, cache,
progress bus, storage, secret cipher, provider-error notices, and the AI
runtime). Only the worker — or the API in the opt-in single-process dev mode
(``APSOR_INGEST_WORKER_ENABLED=true``) — also runs the background loops: the
ingestion poller, the RabbitMQ consumer, the chat-image cleanup sweep, and the
conversation-history indexer.

This module is entrypoint tier, a sibling of ``main.py`` and ``worker.py``. It
wires slices together and must not hold business logic.
"""

import asyncio
import logging
from collections.abc import Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from starlette.datastructures import State

from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.cache.progress_bus import build_progress_bus
from app.infrastructure.cache.resilient_cache import build_cache
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.queue.rabbitmq import RabbitMQJobConsumer
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.agent.dependencies import load_agent_runtime_config
from app.module.agent.service.chat_attachment_cleanup import ChatAttachmentCleanup
from app.module.agent.service.history_indexer import AgentHistoryIndexer
from app.module.knowledge.dependencies import (
    build_embedding_backfill,
    build_history_chunk_store,
    build_ingest_worker,
    build_job_consumer,
    build_provider_refresh,
    build_thumbnail_backfill,
    ingest_runtime_defaults,
    load_ingest_runtime_config,
    reload_ai_runtime,
)
from app.module.knowledge.service.embedding_backfill import EmbeddingBackfill
from app.module.knowledge.service.ingest_job_service import IngestWorker
from app.module.knowledge.service.provider_error_notice_service import (
    ProviderErrorNoticeService,
)
from app.module.knowledge.service.thumbnail_backfill import FileThumbnailBackfill

logger = logging.getLogger(__name__)


async def open_process_state(state: State, settings: Settings) -> None:
    """Create the process-wide resources on ``state`` and load providers.

    The caller owns ``state`` and must call :func:`close_process_state` when the
    process stops, even if this coroutine raises after partially succeeding.
    """
    state.settings = settings
    state.db = Database(settings.database_url, echo=settings.debug)
    state.cache = build_cache(settings.cache_url)
    state.progress_bus = build_progress_bus(settings.cache_url)
    state.storage = build_file_storage(settings)
    cipher = SecretCipher.from_settings(settings)
    notice_service = ProviderErrorNoticeService(state.db.session_factory)
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cipher,
        defaults=provider_defaults_from_settings(settings),
        reporter=notice_service.report,
    )
    await reload_ai_runtime(runtime, state.db.session_factory)
    state.secret_cipher = cipher
    state.ai_runtime = runtime
    state.provider_notice_service = notice_service


async def close_process_state(state: State) -> None:
    """Release whatever :func:`open_process_state` managed to create."""
    progress_bus = getattr(state, "progress_bus", None)
    if progress_bus is not None:
        await progress_bus.close()
    cache = getattr(state, "cache", None)
    if cache is not None:
        await cache.close()
    database = getattr(state, "db", None)
    if database is not None:
        await database.dispose()


async def build_state_ingest_worker(
    state: State,
    settings: Settings,
    *,
    load_config: bool = True,
) -> IngestWorker:
    """Build the durable-ingestion worker over an opened process ``state``.

    With ``load_config`` the worker reads the database-backed runtime limits
    now and before each claim; without it (tests) it uses the environment
    defaults only.
    """
    database: Database = state.db
    defaults = ingest_runtime_defaults(settings)
    config = defaults
    if load_config:
        config = await load_ingest_runtime_config(database.session_factory, defaults)
    return build_ingest_worker(
        state,
        database.session_factory,
        settings,
        runtime_config=config,
        config_provider=(
            (lambda: load_ingest_runtime_config(database.session_factory, defaults))
            if load_config
            else None
        ),
        provider_refresh=build_provider_refresh(state.ai_runtime, database.session_factory),
        progress_bus=state.progress_bus,
    )


@dataclass
class BackgroundServices:
    """The worker-owned loops: ingestion, dispatch consumer, cleanup, history."""

    worker: IngestWorker
    cleanup: ChatAttachmentCleanup
    history_indexer: AgentHistoryIndexer
    consumer: RabbitMQJobConsumer | None = None
    # Only the dedicated worker process starts the backfills (see worker.py).
    thumbnail_backfill: FileThumbnailBackfill | None = None
    embedding_backfill: EmbeddingBackfill | None = None
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)

    def _spawn(self, coroutine: Coroutine[Any, Any, None], name: str) -> None:
        self._tasks.append(asyncio.create_task(coroutine, name=name))

    def start_side_loops(self, settings: Settings, stop_event: asyncio.Event | None) -> None:
        """Start the consumer, cleanup, and history loops as background tasks."""
        self.consumer = build_job_consumer(settings, self.worker)
        if self.consumer is not None:
            self._spawn(self.consumer.run(), "ingest-rabbitmq-consumer")
        self._spawn(self.cleanup.run_forever(stop_event), "chat-attachment-cleanup")
        self._spawn(
            self.history_indexer.run_forever(stop_event),
            "conversation-history-indexer",
        )

    def start_thumbnail_backfill(self, stop_event: asyncio.Event | None) -> None:
        """Start the WebP thumbnail backfill loop (dedicated worker only)."""
        if self.thumbnail_backfill is not None:
            self._spawn(
                self.thumbnail_backfill.run_forever(stop_event),
                "file-thumbnail-backfill",
            )

    def start_embedding_backfill(self, stop_event: asyncio.Event | None) -> None:
        """Start the pending-embedding backfill loop (dedicated worker only)."""
        if self.embedding_backfill is not None:
            self._spawn(
                self.embedding_backfill.run_forever(stop_event),
                "embedding-backfill",
            )

    def start_worker_loop(self) -> None:
        """Run the ingestion poller as a background task (API dev mode)."""
        self._spawn(self.worker.run_forever(), "ingest-worker")

    async def stop(self) -> None:
        """Cancel every started loop, close the consumer, and free the pool."""
        for task in reversed(self._tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self.consumer is not None:
            await self.consumer.close()
            self.consumer = None
        self.worker.close()


async def build_background_services(state: State, settings: Settings) -> BackgroundServices:
    """Assemble the worker-owned loops over an opened process ``state``."""
    database: Database = state.db
    worker = await build_state_ingest_worker(state, settings)
    cleanup = ChatAttachmentCleanup(
        database=database,
        storage=state.storage,
        config_provider=lambda: load_agent_runtime_config(database),
    )
    history_indexer = AgentHistoryIndexer(
        database=database,
        store_factory=lambda session, user_id: build_history_chunk_store(
            state,
            session,
            user_id=user_id,
        ),
        cache=state.cache,
    )
    await worker.startup()
    return BackgroundServices(
        worker=worker,
        cleanup=cleanup,
        history_indexer=history_indexer,
        thumbnail_backfill=(
            build_thumbnail_backfill(state, database)
            if settings.thumbnail_backfill_enabled
            else None
        ),
        embedding_backfill=(
            build_embedding_backfill(state, database)
            if settings.embedding_backfill_enabled
            else None
        ),
    )
