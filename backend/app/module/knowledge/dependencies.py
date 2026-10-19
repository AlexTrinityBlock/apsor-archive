"""Composition root for the knowledge slice."""

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.vision_extractor import (
    DeepSeekVisionExtractor,
    NullVisionExtractor,
)
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database, get_db_session
from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.protocol.vision_extractor_protocol import VisionExtractorProtocol
from app.module.knowledge.repository.ai_config_repository import AiProviderConfigRepository
from app.module.knowledge.repository.chunk_repository import ChunkRepository
from app.module.knowledge.repository.file_repository import FileRepository
from app.module.knowledge.repository.ingest_config_repository import (
    IngestConfigRepository,
)
from app.module.knowledge.repository.ingest_job_repository import IngestJobRepository
from app.module.knowledge.repository.memory_repository import MemoryRepository
from app.module.knowledge.repository.stats_repository import StatsRepository
from app.module.knowledge.repository.summary_repository import SummaryRepository
from app.module.knowledge.repository.tree_repository import TreeRepository
from app.module.knowledge.service.ai_config_service import AiConfigService
from app.module.knowledge.service.ai_service import AiService
from app.module.knowledge.service.demo_service import DemoService
from app.module.knowledge.service.file_service import CpuRunner, FileService
from app.module.knowledge.service.indexer_service import IndexerService
from app.module.knowledge.service.ingest_job_service import IngestJobService, IngestWorker
from app.module.knowledge.service.ingest_settings_service import IngestSettingsService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.search_service import SearchService
from app.module.knowledge.service.stats_service import StatsService
from app.module.knowledge.service.summary_service import SummaryService
from app.module.knowledge.service.timeline_service import TimelineService
from app.module.knowledge.service.tree_service import TreeService


def get_cache(request: Request) -> CacheProtocol:
    return cast(CacheProtocol, request.app.state.cache)


def get_ai_runtime(request: Request) -> AiRuntime:
    return cast(AiRuntime, request.app.state.ai_runtime)


def get_secret_cipher(request: Request) -> SecretCipherProtocol:
    return cast(SecretCipherProtocol, request.app.state.secret_cipher)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_embedder(request: Request) -> EmbedderProtocol:
    return get_ai_runtime(request).embedder


def get_text_generator(request: Request) -> TextGeneratorProtocol:
    return get_ai_runtime(request).text_generator


def get_storage(request: Request) -> FileStorageProtocol:
    return cast(FileStorageProtocol, request.app.state.storage)


def _vision_extractor_for_state(state: State) -> VisionExtractorProtocol:
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    chat_config = runtime.chat_config
    if (
        chat_config.enabled
        and chat_config.provider != "none"
        and chat_config.api_key
    ):
        return DeepSeekVisionExtractor(
            api_key=chat_config.api_key,
            base_url=chat_config.base_url or settings.deepseek_base_url,
            model=chat_config.model,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )
    return NullVisionExtractor()


def _make_cpu_runner(
    pool: ThreadPoolExecutor,
    slots: asyncio.Semaphore,
) -> CpuRunner:
    """Adapt a bounded thread pool to the file service's async CPU hook.

    The pool may be sized above the current setting so it can be reused after a
    database setting change; ``slots`` is the per-worker concurrency gate that
    actually limits extraction work. New jobs get the current gate while jobs
    already in flight finish with the gate they started with.
    """

    async def run_cpu(
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        loop = asyncio.get_running_loop()
        async with slots:
            return await loop.run_in_executor(pool, partial(func, *args, **kwargs))

    return run_cpu


def build_file_service_for_state(
    state: State,
    session: AsyncSession,
    *,
    runtime_config: IngestRuntimeConfig | None = None,
    cpu_runner: CpuRunner | None = None,
    embedding_semaphore: asyncio.Semaphore | None = None,
    fail_on_embedding_error: bool = False,
) -> FileService:
    """Compose the file service without a request, for workers and the API."""
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    chunk_repository = ChunkRepository(session)
    indexer = IndexerService(
        chunk_repository,
        runtime.embedder,
        embedding_batch_size=settings.ingest_embedding_batch_size,
        embedding_concurrency=(
            runtime_config.embedding_concurrency
            if runtime_config is not None
            else settings.ingest_embedding_concurrency
        ),
        embedding_semaphore=embedding_semaphore,
        embedding_max_attempts=settings.ingest_embedding_max_attempts,
        embedding_retry_seconds=settings.ingest_embedding_retry_seconds,
        fail_on_embedding_error=fail_on_embedding_error,
    )
    return FileService(
        file_repository=FileRepository(session),
        tree_repository=TreeRepository(session),
        chunk_repository=chunk_repository,
        indexer=indexer,
        storage=cast(FileStorageProtocol, state.storage),
        cache=cast(CacheProtocol, state.cache),
        text_generator=runtime.text_generator,
        vision_extractor=_vision_extractor_for_state(state),
        target_chars=(
            runtime_config.chunk_target_chars
            if runtime_config is not None
            else settings.chunk_target_chars
        ),
        overlap_chars=(
            runtime_config.chunk_overlap_chars
            if runtime_config is not None
            else settings.chunk_overlap_chars
        ),
        max_chunks=settings.max_chunks_per_file,
        max_upload_bytes=settings.max_upload_bytes,
        max_text_bytes=settings.max_text_bytes,
        vision_max_pages=settings.vision_max_pages,
        pdf_text_threshold=settings.pdf_text_threshold,
        cpu_runner=cpu_runner,
    )


def build_ingest_worker(
    state: State,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    runtime_config: IngestRuntimeConfig | None = None,
    config_provider: Callable[[], Awaitable[IngestRuntimeConfig]] | None = None,
) -> IngestWorker:
    """Build the shared worker used by lifespan mode and the CLI entrypoint.

    Extraction/chunking share one ``ThreadPoolExecutor`` sized for the maximum
    supported setting. A per-runtime semaphore enforces the current database
    value, so lowering or raising ``extract_workers`` affects newly claimed jobs
    without replacing the process. The same pattern applies to embedding
    concurrency and the in-flight job cap.
    """
    initial_config = runtime_config or ingest_runtime_defaults(settings)
    extract_pool = ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix="ingest-extract",
    )
    extract_slots = asyncio.Semaphore(max(1, initial_config.extract_workers))
    embedding_slots = asyncio.Semaphore(
        max(1, initial_config.embedding_concurrency)
    )

    def file_service_factory(
        session: AsyncSession,
        config: IngestRuntimeConfig,
        current_extract_slots: asyncio.Semaphore,
        current_embedding_slots: asyncio.Semaphore,
    ) -> FileService:
        return build_file_service_for_state(
            state,
            session,
            runtime_config=config,
            cpu_runner=_make_cpu_runner(extract_pool, current_extract_slots),
            embedding_semaphore=current_embedding_slots,
            fail_on_embedding_error=True,
        )

    return IngestWorker(
        session_factory=session_factory,
        file_service_factory=file_service_factory,
        storage=cast(FileStorageProtocol, state.storage),
        max_attempts=settings.ingest_job_max_attempts,
        runtime_config=initial_config,
        config_provider=config_provider,
        stale_seconds=settings.ingest_job_stale_seconds,
        extract_pool=extract_pool,
        extract_semaphore=extract_slots,
        embedding_semaphore=embedding_slots,
    )


def _services(
    request: Request,
    session: AsyncSession,
) -> tuple[
    FileService,
    SummaryService,
    MemoryService,
    SearchService,
    AiService,
    TimelineService,
    TreeService,
    StatsService,
]:
    state = request.app.state
    settings = cast(Settings, state.settings)
    cache = get_cache(request)
    runtime = get_ai_runtime(request)
    embedder = runtime.embedder
    text_generator = runtime.text_generator

    chunk_repository = ChunkRepository(session)
    file_repository = FileRepository(session)
    memory_repository = MemoryRepository(session)
    summary_repository = SummaryRepository(session)
    tree_repository = TreeRepository(session)
    indexer = IndexerService(
        chunk_repository,
        embedder,
        embedding_concurrency=settings.ingest_embedding_concurrency,
        embedding_max_attempts=settings.ingest_embedding_max_attempts,
        embedding_retry_seconds=settings.ingest_embedding_retry_seconds,
    )

    summary_service = SummaryService(
        memory_repository=memory_repository,
        summary_repository=summary_repository,
        indexer=indexer,
        text_generator=text_generator,
        cache=cache,
        ai_summary_enabled=settings.ai_summary_enabled,
        auto_summary_threshold=settings.auto_summary_threshold,
        min_memories=settings.summary_min_memories,
    )
    file_service = build_file_service_for_state(state, session)
    memory_service = MemoryService(
        memory_repository=memory_repository,
        chunk_repository=chunk_repository,
        indexer=indexer,
        cache=cache,
        summary_service=summary_service,
    )
    search_service = SearchService(
        chunk_repository=chunk_repository,
        file_repository=file_repository,
        memory_repository=memory_repository,
        summary_repository=summary_repository,
        embedder=embedder,
        cache=cache,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        candidate_limit=settings.search_candidate_limit,
        vector_scan_limit=settings.search_vector_scan_limit,
    )
    ai_service = AiService(
        search_service=search_service,
        text_generator=text_generator,
        embedding_provider=runtime.embedding_config.provider,
        embedding_model=embedder.model_name,
        vector_enabled=runtime.vector_enabled,
    )
    timeline_service = TimelineService(
        memory_repository=memory_repository,
        summary_repository=summary_repository,
        file_repository=file_repository,
        cache=cache,
        cache_ttl_seconds=settings.cache_ttl_seconds,
        timezone_name=settings.timezone,
        max_day_range=settings.timeline_max_day_range,
    )
    tree_service = TreeService(
        tree_repository=tree_repository,
        cache=cache,
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )
    stats_service = StatsService(
        stats_repository=StatsRepository(session),
        cache=cache,
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )
    return (
        file_service,
        summary_service,
        memory_service,
        search_service,
        ai_service,
        timeline_service,
        tree_service,
        stats_service,
    )


def get_file_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> FileService:
    return build_file_service_for_state(request.app.state, session)


def get_ingest_job_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestJobService:
    settings = cast(Settings, request.app.state.settings)
    return IngestJobService(
        repository=IngestJobRepository(session),
        file_service=build_file_service_for_state(request.app.state, session),
        max_attempts=settings.ingest_job_max_attempts,
    )


def get_summary_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> SummaryService:
    return _services(request, session)[1]


def get_memory_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> MemoryService:
    return _services(request, session)[2]


def get_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> SearchService:
    return _services(request, session)[3]


def get_ai_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AiService:
    return _services(request, session)[4]


def get_timeline_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TimelineService:
    return _services(request, session)[5]


def get_tree_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TreeService:
    return _services(request, session)[6]


def get_stats_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> StatsService:
    return _services(request, session)[7]


def get_demo_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    file_service: FileService = Depends(get_file_service),
    memory_service: MemoryService = Depends(get_memory_service),
    summary_service: SummaryService = Depends(get_summary_service),
) -> DemoService:
    return DemoService(
        file_service=file_service,
        memory_service=memory_service,
        summary_service=summary_service,
        file_repository=FileRepository(session),
        memory_repository=MemoryRepository(session),
    )


def get_ai_config_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AiConfigService:
    runtime = get_ai_runtime(request)
    return AiConfigService(
        repository=AiProviderConfigRepository(session),
        runtime=runtime,
        cipher=get_secret_cipher(request),
        defaults=runtime.defaults,
        chunk_repository=ChunkRepository(session),
        cache=get_cache(request),
    )


def ingest_runtime_defaults(settings: Settings) -> IngestRuntimeConfig:
    """Build the fresh-install defaults from the application environment.

    The chunk sizes intentionally reuse the existing ``chunk_target_chars`` and
    ``chunk_overlap_chars`` environment names so the synchronous ingestion path
    and the worker share one default until the database row is edited.
    """
    return IngestRuntimeConfig(
        poll_seconds=settings.ingest_poll_seconds,
        extract_workers=settings.ingest_extract_workers,
        max_inflight_jobs=settings.ingest_max_inflight_jobs,
        embedding_concurrency=settings.ingest_embedding_concurrency,
        chunk_target_chars=settings.chunk_target_chars,
        chunk_overlap_chars=settings.chunk_overlap_chars,
    )


def get_ingest_settings_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestSettingsService:
    """Build settings CRUD on the request transaction."""
    return IngestSettingsService(
        IngestConfigRepository(session),
        defaults=ingest_runtime_defaults(get_app_settings(request)),
    )


async def load_ingest_runtime_config(
    session_factory: async_sessionmaker[AsyncSession],
    defaults: IngestRuntimeConfig,
) -> IngestRuntimeConfig:
    """Load one immutable snapshot using a short-lived worker session."""
    async with session_factory() as session:
        service = IngestSettingsService(
            IngestConfigRepository(session),
            defaults=defaults,
        )
        config = await service.get_runtime_config()
        await session.commit()
    return config


async def get_ingest_runtime_config(request: Request) -> IngestRuntimeConfig:
    """Load one immutable snapshot for a worker loop or job.

    The read uses its own short-lived session instead of the request session so
    a streaming or long-lived worker caller never holds a connection open.
    """
    database = cast(Database, request.app.state.db)
    defaults = ingest_runtime_defaults(get_app_settings(request))
    return await load_ingest_runtime_config(database.session_factory, defaults)
