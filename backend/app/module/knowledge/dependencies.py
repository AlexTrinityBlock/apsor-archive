"""Composition root for the knowledge slice.

Every private-archive service is built for one acting account. The FastAPI
``get_*_service`` dependencies resolve that account with
``require_authenticated`` and pass its ``user_id`` down. Worker and agent
callers use the explicit ``build_*`` functions with the owner they already
resolved.

Global configuration services (providers, ingestion runtime) are root-only and
read the singleton config rows through the root request context or a
``system_session``.
"""

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from app.dependency.auth import require_authenticated, require_root
from app.infrastructure.ai.provider_factory import ProviderClientTester, ProviderFactory
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.vision_extractor import (
    DeepSeekVisionExtractor,
    NullVisionExtractor,
)
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import (
    Database,
    get_db_session,
    system_session,
)
from app.module.auth.schema.auth_schema import UserSchema
from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.provider_tester_protocol import ProviderTesterProtocol
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.protocol.vision_extractor_protocol import VisionExtractorProtocol
from app.module.knowledge.repository.chunk_repository import ChunkRepository
from app.module.knowledge.repository.file_repository import FileRepository
from app.module.knowledge.repository.folder_repository import FolderRepository
from app.module.knowledge.repository.ingest_config_repository import (
    IngestConfigRepository,
)
from app.module.knowledge.repository.ingest_job_repository import IngestJobRepository
from app.module.knowledge.repository.memory_repository import MemoryRepository
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)
from app.module.knowledge.repository.stats_repository import StatsRepository
from app.module.knowledge.repository.summary_repository import SummaryRepository
from app.module.knowledge.service.ai_service import AiService
from app.module.knowledge.service.file_service import CpuRunner, FileService
from app.module.knowledge.service.indexer_service import IndexerService
from app.module.knowledge.service.ingest_job_service import IngestJobService, IngestWorker
from app.module.knowledge.service.ingest_settings_service import IngestSettingsService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.provider_config_service import ProviderConfigService
from app.module.knowledge.service.search_service import SearchService
from app.module.knowledge.service.stats_service import StatsService
from app.module.knowledge.service.summary_service import SummaryService
from app.module.knowledge.service.timeline_service import TimelineService


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
    if chat_config.enabled and chat_config.provider != "none" and chat_config.api_key:
        return DeepSeekVisionExtractor(
            api_key=chat_config.api_key,
            base_url=chat_config.base_url or settings.deepseek_base_url,
            model=chat_config.model or settings.deepseek_model,
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


def _build_indexer(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    embedding_semaphore: asyncio.Semaphore | None = None,
    fail_on_embedding_error: bool = False,
) -> tuple[ChunkRepository, IndexerService]:
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    chunk_repository = ChunkRepository(session, user_id)
    indexer = IndexerService(
        chunk_repository,
        runtime.embedder,
        user_id=user_id,
        embedding_batch_size=settings.ingest_embedding_batch_size,
        embedding_concurrency=settings.ingest_embedding_concurrency,
        embedding_semaphore=embedding_semaphore,
        embedding_max_attempts=settings.ingest_embedding_max_attempts,
        embedding_retry_seconds=settings.ingest_embedding_retry_seconds,
        fail_on_embedding_error=fail_on_embedding_error,
    )
    return chunk_repository, indexer


def build_file_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    runtime_config: IngestRuntimeConfig | None = None,
    cpu_runner: CpuRunner | None = None,
    embedding_semaphore: asyncio.Semaphore | None = None,
    fail_on_embedding_error: bool = False,
) -> FileService:
    """Compose a file service for one owner, for requests, workers, and tools."""
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    chunk_repository = ChunkRepository(session, user_id)
    indexer = IndexerService(
        chunk_repository,
        runtime.embedder,
        user_id=user_id,
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
        user_id=user_id,
        file_repository=FileRepository(session, user_id),
        folder_repository=FolderRepository(session, user_id),
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


def build_summary_service(state: State, session: AsyncSession, *, user_id: int) -> SummaryService:
    """Compose an owner-scoped summary service."""
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    _, indexer = _build_indexer(state, session, user_id=user_id)
    return SummaryService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        summary_repository=SummaryRepository(session, user_id),
        indexer=indexer,
        text_generator=runtime.text_generator,
        cache=cast(CacheProtocol, state.cache),
        ai_summary_enabled=settings.ai_summary_enabled,
        auto_summary_threshold=settings.auto_summary_threshold,
        min_memories=settings.summary_min_memories,
    )


def build_memory_service(state: State, session: AsyncSession, *, user_id: int) -> MemoryService:
    """Compose an owner-scoped memory service, including its auto-summary hook."""
    runtime = cast(AiRuntime, state.ai_runtime)
    chunk_repository, indexer = _build_indexer(state, session, user_id=user_id)
    return MemoryService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        chunk_repository=chunk_repository,
        indexer=indexer,
        cache=cast(CacheProtocol, state.cache),
        summary_service=build_summary_service(state, session, user_id=user_id),
        text_generator=runtime.text_generator,
    )


def build_search_service(state: State, session: AsyncSession, *, user_id: int) -> SearchService:
    """Compose an owner-scoped hybrid search service."""
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    return SearchService(
        user_id=user_id,
        chunk_repository=ChunkRepository(session, user_id),
        file_repository=FileRepository(session, user_id),
        memory_repository=MemoryRepository(session, user_id),
        summary_repository=SummaryRepository(session, user_id),
        embedder=runtime.embedder,
        cache=cast(CacheProtocol, state.cache),
        cache_ttl_seconds=settings.cache_ttl_seconds,
        candidate_limit=settings.search_candidate_limit,
        vector_scan_limit=settings.search_vector_scan_limit,
    )


def build_timeline_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> TimelineService:
    """Compose an owner-scoped timeline service."""
    settings = cast(Settings, state.settings)
    return TimelineService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        summary_repository=SummaryRepository(session, user_id),
        file_repository=FileRepository(session, user_id),
        cache=cast(CacheProtocol, state.cache),
        cache_ttl_seconds=settings.cache_ttl_seconds,
        timezone_name=settings.timezone,
        max_day_range=settings.timeline_max_day_range,
    )


def build_stats_service(state: State, session: AsyncSession, *, user_id: int) -> StatsService:
    """Compose an owner-scoped dashboard statistics service."""
    settings = cast(Settings, state.settings)
    return StatsService(
        user_id=user_id,
        stats_repository=StatsRepository(session, user_id),
        cache=cast(CacheProtocol, state.cache),
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )


def build_ai_service(state: State) -> AiService:
    """Compose the read-only global AI status service. It has no private rows."""
    runtime = cast(AiRuntime, state.ai_runtime)
    return AiService(
        text_generator=runtime.text_generator,
        chat_provider=runtime.chat_config.provider,
        chat_model=runtime.chat_config.model,
        embedding_provider=runtime.embedding_config.provider,
        embedding_model=runtime.embedder.model_name,
        vector_enabled=runtime.vector_enabled,
    )


def build_ingest_job_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> IngestJobService:
    """Compose the request-scoped ingestion queue service for one owner."""
    settings = cast(Settings, state.settings)
    return IngestJobService(
        user_id=user_id,
        repository=IngestJobRepository(session, user_id),
        file_service=build_file_service(state, session, user_id=user_id),
        max_attempts=settings.ingest_job_max_attempts,
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
    embedding_slots = asyncio.Semaphore(max(1, initial_config.embedding_concurrency))

    def file_service_factory(
        session: AsyncSession,
        user_id: int,
        config: IngestRuntimeConfig,
        current_extract_slots: asyncio.Semaphore,
        current_embedding_slots: asyncio.Semaphore,
    ) -> FileService:
        return build_file_service(
            state,
            session,
            user_id=user_id,
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


def get_file_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> FileService:
    return build_file_service(request.app.state, session, user_id=user.user_id)


def get_ingest_job_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> IngestJobService:
    return build_ingest_job_service(request.app.state, session, user_id=user.user_id)


def get_summary_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> SummaryService:
    return build_summary_service(request.app.state, session, user_id=user.user_id)


def get_memory_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> MemoryService:
    return build_memory_service(request.app.state, session, user_id=user.user_id)


def get_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> SearchService:
    return build_search_service(request.app.state, session, user_id=user.user_id)


def get_ai_service(
    request: Request,
    _user: UserSchema = Depends(require_authenticated),
) -> AiService:
    """The AI status payload is global configuration, not private archive data."""
    return build_ai_service(request.app.state)


def get_timeline_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> TimelineService:
    return build_timeline_service(request.app.state, session, user_id=user.user_id)


def get_stats_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> StatsService:
    return build_stats_service(request.app.state, session, user_id=user.user_id)


def get_provider_config_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_root),
) -> ProviderConfigService:
    """Build the root-only registry service on the root request transaction.

    Global provider configuration is read through this root session. Embedding
    reindex receives the application ``Database`` so it can enumerate chunk
    owners in a maintenance scope and then update each owner only inside that
    owner's ``user_session``.

    Tests set ``app.state.provider_tester`` to a deterministic fake so creating
    or testing a provider never reaches DeepSeek, OpenAI, or Tavily.
    """
    runtime = get_ai_runtime(request)
    tester = getattr(request.app.state, "provider_tester", None)
    if tester is None:
        settings = get_app_settings(request)
        tester = ProviderClientTester(ProviderFactory(settings), settings)
    return ProviderConfigService(
        user_id=user.user_id,
        database=cast(Database, request.app.state.db),
        repository=ProviderConfigRepository(session),
        runtime=runtime,
        cipher=get_secret_cipher(request),
        defaults=runtime.defaults,
        chunk_repository_factory=ChunkRepository,
        cache=get_cache(request),
        tester=cast(ProviderTesterProtocol, tester),
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
    _user: UserSchema = Depends(require_root),
) -> IngestSettingsService:
    """Build root-only settings CRUD on the root request transaction."""
    return IngestSettingsService(
        IngestConfigRepository(session),
        defaults=ingest_runtime_defaults(get_app_settings(request)),
    )


async def load_ingest_runtime_config(
    session_factory: async_sessionmaker[AsyncSession],
    defaults: IngestRuntimeConfig,
) -> IngestRuntimeConfig:
    """Load one immutable snapshot through a root system session.

    The ingestion config is a global singleton; the worker reads it without any
    user context because it is not private archive data.
    """
    async with system_session(session_factory) as session:
        service = IngestSettingsService(
            IngestConfigRepository(session),
            defaults=defaults,
        )
        return await service.get_runtime_config()


async def get_ingest_runtime_config(request: Request) -> IngestRuntimeConfig:
    """Load one immutable snapshot for a worker loop or job.

    The read uses its own short-lived system session instead of the request
    session so a streaming or long-lived worker caller never holds a connection
    open.
    """
    database = cast(Database, request.app.state.db)
    defaults = ingest_runtime_defaults(get_app_settings(request))
    return await load_ingest_runtime_config(database.session_factory, defaults)
