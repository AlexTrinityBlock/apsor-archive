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

from app.dependency.auth import (
    require_authenticated,
    require_root,
    require_stateless_authenticated,
)
from app.infrastructure.ai.anthropic_vision import AnthropicVisionExtractor
from app.infrastructure.ai.probe import ProviderProbe
from app.infrastructure.ai.provider_factory import ProviderClientTester, ProviderFactory
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.user_models import (
    ChatAssignment,
    build_user_text_generator,
    load_assignment,
    resolve_endpoint,
    slot_values,
)
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
from app.infrastructure.queue.rabbitmq import RabbitMQJobConsumer, RabbitMQJobNotifier
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.knowledge.domain.ingest_config_domain import (
    IngestRuntimeConfig,
    normalize_vision_description_language,
)
from app.module.knowledge.domain.ingest_progress_domain import ProgressTracker
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    DEFAULT_VISION_IMAGE_PROMPT,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.job_notifier_protocol import (
    JobNotifierProtocol,
    NullJobNotifier,
)
from app.module.knowledge.protocol.progress_bus_protocol import (
    NullProgressBus,
    ProgressBusProtocol,
)
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
from app.module.knowledge.repository.model_assignment_repository import (
    ModelAssignmentRepository,
)
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)
from app.module.knowledge.repository.stats_repository import StatsRepository
from app.module.knowledge.repository.summary_repository import SummaryRepository
from app.module.knowledge.service.ai_service import AiService
from app.module.knowledge.service.file_service import CpuRunner, FileService
from app.module.knowledge.service.history_chunk_store import HistoryChunkStore
from app.module.knowledge.service.indexer_service import IndexerService
from app.module.knowledge.service.ingest_job_service import IngestJobService, IngestWorker
from app.module.knowledge.service.ingest_progress_service import IngestProgressService
from app.module.knowledge.service.ingest_settings_service import IngestSettingsService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.metered_text_generator import MeteredTextGenerator
from app.module.knowledge.service.model_assignment_service import (
    ModelAssignmentService,
)
from app.module.knowledge.service.provider_config_service import ProviderConfigService
from app.module.knowledge.service.provider_error_notice_service import (
    ProviderErrorNoticeService,
)
from app.module.knowledge.service.related_memory_service import RelatedMemoryService
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


def _vision_extractor_for_state(
    state: State,
    assignment: ChatAssignment,
) -> VisionExtractorProtocol:
    """Select vision extraction from the account's auxiliary endpoint.

    Selection follows the resolved auxiliary row, exactly like background text
    generation: the assigned row id is looked up in the runtime chain, and only
    that row's provider family decides between the Anthropic and DeepSeek
    extractors. There is no scan for "some usable provider" and no fallback to
    ``runtime.chat_config``: an account with no auxiliary assignment, or one
    whose row is inactive or keyless, gets :class:`NullVisionExtractor` and the
    existing ``ai_not_configured`` behaviour. The ``app.state.vision_extractor``
    test seam still wins before any of this.
    """
    override = getattr(state, "vision_extractor", None)
    if override is not None:
        return cast(VisionExtractorProtocol, override)
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    values = slot_values(assignment, "auxiliary")
    if values.row_id is None:
        return NullVisionExtractor()
    resolved = resolve_endpoint(runtime.chat_chain, values.row_id)
    if (
        resolved is None
        or not resolved.enabled
        or resolved.provider == "none"
        or not resolved.api_key
    ):
        return NullVisionExtractor()
    model = values.model or resolved.model
    if not model:
        return NullVisionExtractor()
    if resolved.provider == "anthropic":
        return AnthropicVisionExtractor(
            api_key=resolved.api_key,
            base_url=resolved.base_url or settings.anthropic_base_url,
            model=model,
            timeout_seconds=settings.anthropic_timeout_seconds,
            reasoning_effort=values.effort,
        )
    if resolved.provider == "deepseek":
        return DeepSeekVisionExtractor(
            api_key=resolved.api_key,
            base_url=resolved.base_url or settings.deepseek_base_url,
            model=model,
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
    embedding_refresh: Callable[[], Awaitable[EmbedderProtocol]] | None = None,
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
        embedding_refresh=embedding_refresh,
        quota=AccountQuotaService(cast(Database, state.db), user_id),
    )
    return chunk_repository, indexer


async def build_file_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    runtime_config: IngestRuntimeConfig | None = None,
    vision_description_language: str | None = None,
    vision_image_prompt: str | None = None,
    vision_document_prompt: str | None = None,
    cpu_runner: CpuRunner | None = None,
    embedding_semaphore: asyncio.Semaphore | None = None,
    fail_on_embedding_error: bool = False,
    embedding_refresh: Callable[[], Awaitable[EmbedderProtocol]] | None = None,
    progress_tracker: ProgressTracker | None = None,
) -> FileService:
    """Compose a file service for one owner, for requests, workers, and tools.

    Titles, tags, document analysis, and extraction use the account's auxiliary
    endpoint, read from ``app_user`` in the caller's session. An unassigned,
    inactive, or keyless slot yields the null generator, so the existing
    ``ai_not_configured`` behaviour is preserved without falling back to another
    provider. Vision follows the same resolved auxiliary row.

    ``embedding_refresh`` is supplied only by the durable worker. It lets the
    indexer recover from one mid-job 401/403 without switching the model or
    dimension underneath a running job. ``progress_tracker`` is also
    worker-only: request-path and agent ingestion stay indeterminate, while a
    durable job shares one tracker between extraction and the progress reporter.
    """
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    assignment = await load_assignment(session, user_id)
    built = build_user_text_generator(runtime, assignment, slot="auxiliary")
    if vision_description_language is not None:
        resolved_vision_language = normalize_vision_description_language(
            vision_description_language
        )
    elif runtime_config is not None:
        resolved_vision_language = runtime_config.vision_description_language
    else:
        resolved_vision_language = normalize_vision_description_language(
            settings.vision_description_language
        )
    resolved_image_prompt = (
        vision_image_prompt
        if vision_image_prompt is not None
        else (
            runtime_config.vision_image_prompt
            if runtime_config is not None
            else DEFAULT_VISION_IMAGE_PROMPT
        )
    )
    resolved_document_prompt = (
        vision_document_prompt
        if vision_document_prompt is not None
        else (
            runtime_config.vision_document_prompt
            if runtime_config is not None
            else DEFAULT_VISION_DOCUMENT_PROMPT
        )
    )
    chunk_repository = ChunkRepository(session, user_id)
    quota = AccountQuotaService(cast(Database, state.db), user_id)
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
        embedding_refresh=embedding_refresh,
        quota=quota,
    )
    return FileService(
        user_id=user_id,
        file_repository=FileRepository(session, user_id),
        folder_repository=FolderRepository(session, user_id),
        chunk_repository=chunk_repository,
        indexer=indexer,
        storage=cast(FileStorageProtocol, state.storage),
        cache=cast(CacheProtocol, state.cache),
        text_generator=MeteredTextGenerator(built.generator, quota),
        vision_extractor=_vision_extractor_for_state(state, assignment),
        vision_description_language=resolved_vision_language,
        vision_image_prompt=resolved_image_prompt,
        vision_document_prompt=resolved_document_prompt,
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
        chat_quota=quota,
        cpu_runner=cpu_runner,
        progress_tracker=progress_tracker,
    )


def build_history_chunk_store(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> HistoryChunkStore:
    """Compose the knowledge-side write adapter for conversation history.

    The agent history indexer supplies fixed 256-character drafts and this
    builder reuses the shared ``IndexerService``, so history chunks follow the
    same n-gram and embedding path as every other source kind.
    """
    chunk_repository, indexer = _build_indexer(state, session, user_id=user_id)
    return HistoryChunkStore(
        user_id=user_id,
        chunk_repository=chunk_repository,
        indexer=indexer,
    )


async def build_summary_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> SummaryService:
    """Compose an owner-scoped summary service on the auxiliary endpoint."""
    settings = cast(Settings, state.settings)
    runtime = cast(AiRuntime, state.ai_runtime)
    assignment = await load_assignment(session, user_id)
    built = build_user_text_generator(runtime, assignment, slot="auxiliary")
    _, indexer = _build_indexer(state, session, user_id=user_id)
    quota = AccountQuotaService(cast(Database, state.db), user_id)
    return SummaryService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        summary_repository=SummaryRepository(session, user_id),
        indexer=indexer,
        text_generator=MeteredTextGenerator(built.generator, quota),
        cache=cast(CacheProtocol, state.cache),
        ai_summary_enabled=settings.ai_summary_enabled,
        auto_summary_threshold=settings.auto_summary_threshold,
        min_memories=settings.summary_min_memories,
    )


async def build_memory_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> MemoryService:
    """Compose an owner-scoped memory service, including its auto-summary hook."""
    runtime = cast(AiRuntime, state.ai_runtime)
    assignment = await load_assignment(session, user_id)
    built = build_user_text_generator(runtime, assignment, slot="auxiliary")
    chunk_repository, indexer = _build_indexer(state, session, user_id=user_id)
    quota = AccountQuotaService(cast(Database, state.db), user_id)
    return MemoryService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        chunk_repository=chunk_repository,
        indexer=indexer,
        cache=cast(CacheProtocol, state.cache),
        summary_service=await build_summary_service(state, session, user_id=user_id),
        text_generator=MeteredTextGenerator(built.generator, quota),
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
        quota=AccountQuotaService(cast(Database, state.db), user_id),
    )


def build_related_memory_service(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> RelatedMemoryService:
    """Compose an owner-scoped related-memory ranker over stored chunks."""
    settings = cast(Settings, state.settings)
    return RelatedMemoryService(
        user_id=user_id,
        memory_repository=MemoryRepository(session, user_id),
        file_repository=FileRepository(session, user_id),
        chunk_repository=ChunkRepository(session, user_id),
        summary_repository=SummaryRepository(session, user_id),
        cache=cast(CacheProtocol, state.cache),
        cache_ttl_seconds=settings.cache_ttl_seconds,
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


def _rabbitmq_url(settings: Settings) -> str:
    """Return the AMQP URL or fail startup with a secret-free message."""
    secret = settings.rabbitmq_url
    url = secret.get_secret_value().strip() if secret is not None else ""
    if not url:
        raise RuntimeError(
            "APSOR_RABBITMQ_ENABLED is true but APSOR_RABBITMQ_URL is not set."
        )
    return url


def build_job_notifier(settings: Settings) -> JobNotifierProtocol:
    """Build the process-wide ingestion wake-up publisher.

    Disabled dispatch returns the no-op notifier, so the API keeps working with
    database polling alone. An enabled deployment without a URL fails startup
    instead of silently running without the advertised queue.
    """
    if not settings.rabbitmq_enabled:
        return NullJobNotifier()
    return RabbitMQJobNotifier(
        url=_rabbitmq_url(settings),
        exchange_name=settings.rabbitmq_ingest_exchange,
        queue_name=settings.rabbitmq_ingest_queue,
        retry_queue_name=settings.rabbitmq_ingest_retry_queue,
        retry_ttl_ms=settings.rabbitmq_retry_ttl_ms,
        connect_timeout_seconds=settings.rabbitmq_connect_timeout_seconds,
        publish_timeout_seconds=settings.rabbitmq_publish_timeout_seconds,
    )


def build_job_consumer(
    settings: Settings,
    worker: IngestWorker,
) -> RabbitMQJobConsumer | None:
    """Build the ingestion consumer for a process that owns the worker."""
    if not settings.rabbitmq_enabled:
        return None
    return RabbitMQJobConsumer(
        url=_rabbitmq_url(settings),
        handler=worker.process_notified_job,
        exchange_name=settings.rabbitmq_ingest_exchange,
        queue_name=settings.rabbitmq_ingest_queue,
        retry_queue_name=settings.rabbitmq_ingest_retry_queue,
        retry_ttl_ms=settings.rabbitmq_retry_ttl_ms,
        max_dispatch_retries=settings.rabbitmq_max_dispatch_retries,
        connect_timeout_seconds=settings.rabbitmq_connect_timeout_seconds,
    )


def get_job_notifier(state: State) -> JobNotifierProtocol:
    """Return the lifespan notifier, or the no-op default for tests."""
    notifier = getattr(state, "job_notifier", None)
    if notifier is None:
        return NullJobNotifier()
    return cast(JobNotifierProtocol, notifier)


async def build_ingest_job_service(
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
        file_service=await build_file_service(state, session, user_id=user_id),
        max_attempts=settings.ingest_job_max_attempts,
        notifier=get_job_notifier(state),
    )


def build_provider_refresh(
    runtime: AiRuntime,
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[EmbedderProtocol]]:
    """Build the worker's provider-refresh callback.

    The worker calls this at a batch boundary (no in-flight job) and once from
    an indexer after a mid-job 401/403. Each call loads the current database
    snapshot through a short-lived system session and returns the embedder that
    snapshot exposes. ``announce=False`` keeps an unchanged routine reload at
    DEBUG; startup and root writes still log the snapshot at INFO.
    """

    async def refresh() -> EmbedderProtocol:
        async with system_session(session_factory) as session:
            await runtime.reload(
                ProviderConfigRepository(session),
                announce=False,
            )
        return runtime.embedder

    return refresh


def build_ingest_worker(
    state: State,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    runtime_config: IngestRuntimeConfig | None = None,
    config_provider: Callable[[], Awaitable[IngestRuntimeConfig]] | None = None,
    provider_refresh: Callable[[], Awaitable[EmbedderProtocol]] | None = None,
    progress_bus: ProgressBusProtocol | None = None,
) -> IngestWorker:
    """Build the shared worker used by lifespan mode and the CLI entrypoint.

    Extraction/chunking share one ``ThreadPoolExecutor`` sized for the maximum
    supported setting. A per-runtime semaphore enforces the current database
    value, so lowering or raising ``extract_workers`` affects newly claimed jobs
    without replacing the process. The same pattern applies to embedding
    concurrency and the in-flight job cap.

    ``provider_refresh`` reloads the AI provider snapshot when the worker has no
    in-flight job, and is also handed to every file service so the indexer can
    recover once from a mid-job authentication failure.
    """
    initial_config = runtime_config or ingest_runtime_defaults(settings)
    extract_pool = ThreadPoolExecutor(
        max_workers=8,
        thread_name_prefix="ingest-extract",
    )
    extract_slots = asyncio.Semaphore(max(1, initial_config.extract_workers))
    embedding_slots = asyncio.Semaphore(max(1, initial_config.embedding_concurrency))

    async def file_service_factory(
        session: AsyncSession,
        user_id: int,
        config: IngestRuntimeConfig,
        current_extract_slots: asyncio.Semaphore,
        current_embedding_slots: asyncio.Semaphore,
        progress_tracker: ProgressTracker | None = None,
    ) -> FileService:
        return await build_file_service(
            state,
            session,
            user_id=user_id,
            runtime_config=config,
            cpu_runner=_make_cpu_runner(extract_pool, current_extract_slots),
            embedding_semaphore=current_embedding_slots,
            fail_on_embedding_error=True,
            embedding_refresh=provider_refresh,
            progress_tracker=progress_tracker,
        )

    return IngestWorker(
        session_factory=session_factory,
        file_service_factory=file_service_factory,
        storage=cast(FileStorageProtocol, state.storage),
        max_attempts=settings.ingest_job_max_attempts,
        runtime_config=initial_config,
        config_provider=config_provider,
        provider_refresh=provider_refresh,
        stale_seconds=settings.ingest_job_stale_seconds,
        extract_pool=extract_pool,
        extract_semaphore=extract_slots,
        embedding_semaphore=embedding_slots,
        progress_bus=progress_bus,
    )


async def get_file_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> FileService:
    return await build_file_service(request.app.state, session, user_id=user.user_id)


async def get_ingest_job_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> IngestJobService:
    return await build_ingest_job_service(
        request.app.state,
        session,
        user_id=user.user_id,
    )


def get_progress_bus(state: State) -> ProgressBusProtocol:
    """Return the lifespan progress bus, or a null bus when it is not built."""
    bus = getattr(state, "progress_bus", None)
    if bus is None:
        return NullProgressBus()
    return cast(ProgressBusProtocol, bus)


def build_ingest_progress_service(
    state: State,
    *,
    user_id: int,
    role: str,
) -> IngestProgressService:
    """Compose the SSE service on short-lived owner sessions, never a request one."""
    return IngestProgressService(
        database=cast(Database, state.db),
        progress_bus=get_progress_bus(state),
        user_id=user_id,
        role=role,
    )


def get_ingest_progress_service(
    request: Request,
    user: UserSchema = Depends(require_stateless_authenticated),
) -> IngestProgressService:
    """Build the streaming progress service without touching the request session.

    ``require_stateless_authenticated`` resolves the cookie in a short public
    session, so the stream never pins the request transaction open.
    """
    return build_ingest_progress_service(
        request.app.state,
        user_id=user.user_id,
        role=user.role,
    )


async def get_summary_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> SummaryService:
    return await build_summary_service(
        request.app.state,
        session,
        user_id=user.user_id,
    )


async def get_memory_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> MemoryService:
    return await build_memory_service(
        request.app.state,
        session,
        user_id=user.user_id,
    )


def get_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> SearchService:
    return build_search_service(request.app.state, session, user_id=user.user_id)


def get_related_memory_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
) -> RelatedMemoryService:
    return build_related_memory_service(request.app.state, session, user_id=user.user_id)


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


def get_provider_notice_service(request: Request) -> ProviderErrorNoticeService:
    """Return the process-wide notice service, or build one from the factory.

    The lifespan stores the same instance that the AI runtime uses for its
    failure reporter, so the request path and provider calls agree on the
    dedupe clock. Tests may inject a service directly on ``app.state``.
    """
    override = getattr(request.app.state, "provider_notice_service", None)
    if override is not None:
        return cast(ProviderErrorNoticeService, override)
    database = cast(Database, request.app.state.db)
    return ProviderErrorNoticeService(database.session_factory)


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
        vision_description_language=settings.vision_description_language,
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


async def load_ingest_runtime_peek(
    session_factory: async_sessionmaker[AsyncSession],
    defaults: IngestRuntimeConfig,
) -> IngestRuntimeConfig:
    """Read one snapshot without creating or repairing the singleton row."""
    async with system_session(session_factory) as session:
        service = IngestSettingsService(
            IngestConfigRepository(session),
            defaults=defaults,
        )
        return await service.peek_runtime_config()


async def get_ingest_runtime_config(request: Request) -> IngestRuntimeConfig:
    """Load one immutable snapshot for a worker loop or job.

    The read uses its own short-lived system session instead of the request
    session so a streaming or long-lived worker caller never holds a connection
    open.
    """
    database = cast(Database, request.app.state.db)
    defaults = ingest_runtime_defaults(get_app_settings(request))
    return await load_ingest_runtime_config(database.session_factory, defaults)


async def get_upload_ingest_runtime_config(request: Request) -> IngestRuntimeConfig:
    """Return the stored upload snapshot without materializing global settings.

    A synchronous upload must not make an absent ``ingest_config`` row exist;
    the settings API remains the only path that lazily creates or repairs it.
    """
    database = cast(Database, request.app.state.db)
    defaults = ingest_runtime_defaults(get_app_settings(request))
    return await load_ingest_runtime_peek(database.session_factory, defaults)


async def get_upload_file_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: UserSchema = Depends(require_authenticated),
    runtime_config: IngestRuntimeConfig = Depends(get_upload_ingest_runtime_config),
) -> FileService:
    """Build the synchronous upload service with the stored vision settings.

    Only ``POST /files`` needs the stored prompts and language; reads, moves,
    copies, deletes, chunk windows, and content keep the plain
    ``get_file_service`` so they do not load the global config on every request.
    The settings read is deliberately non-materializing: uploads never create
    the settings row.
    """
    return await build_file_service(
        request.app.state,
        session,
        user_id=user.user_id,
        runtime_config=runtime_config,
    )


def get_provider_probe(request: Request) -> ProviderProbe:
    """Return the per-request endpoint probe, or the test seam on ``app.state``.

    The probe is stateless and cheap, but one instance per request keeps the
    timeout snapshot and the factory consistent across every changed slot in a
    single save. Tests install a deterministic fake as ``app.state.provider_probe``
    so no assignment test can reach a real provider.
    """
    override = getattr(request.app.state, "provider_probe", None)
    if override is not None:
        return cast(ProviderProbe, override)
    return ProviderProbe(ProviderFactory(get_app_settings(request)))


def build_model_assignment_service(
    request: Request,
    session: AsyncSession,
    *,
    probe: ProviderProbe | None = None,
) -> ModelAssignmentService:
    """Compose the assignment service on the caller's request session.

    The repository reads ``app_user`` (an auth table) and
    ``chat_provider_config`` (a global config table); no private archive row is
    touched. The runtime supplies the resolved chain used for row-id lookups and
    for the stored key a probe needs.
    """
    runtime = get_ai_runtime(request)
    return ModelAssignmentService(
        session=session,
        repository=ModelAssignmentRepository(session),
        runtime=runtime,
        defaults=runtime.defaults,
        probe=probe if probe is not None else get_provider_probe(request),
    )


def get_model_assignment_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    probe: ProviderProbe = Depends(get_provider_probe),
) -> ModelAssignmentService:
    """FastAPI dependency for the assignment router."""
    return build_model_assignment_service(request, session, probe=probe)
