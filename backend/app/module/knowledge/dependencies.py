"""Composition root for the knowledge slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.vision_extractor import (
    DeepSeekVisionExtractor,
    NullVisionExtractor,
)
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import get_db_session
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.repository.ai_config_repository import AiProviderConfigRepository
from app.module.knowledge.repository.chunk_repository import ChunkRepository
from app.module.knowledge.repository.file_repository import FileRepository
from app.module.knowledge.repository.memory_repository import MemoryRepository
from app.module.knowledge.repository.stats_repository import StatsRepository
from app.module.knowledge.repository.summary_repository import SummaryRepository
from app.module.knowledge.repository.tree_repository import TreeRepository
from app.module.knowledge.service.ai_config_service import AiConfigService
from app.module.knowledge.service.ai_service import AiService
from app.module.knowledge.service.demo_service import DemoService
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.indexer_service import IndexerService
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
    settings = request.app.state.settings
    cache = get_cache(request)
    runtime = get_ai_runtime(request)
    embedder = runtime.embedder
    text_generator = runtime.text_generator
    storage = get_storage(request)
    chat_config = runtime.chat_config
    vision_extractor = (
        DeepSeekVisionExtractor(
            api_key=chat_config.api_key,
            base_url=chat_config.base_url or settings.deepseek_base_url,
            model=chat_config.model,
            timeout_seconds=settings.deepseek_timeout_seconds,
        )
        if chat_config.enabled
        and chat_config.provider != "none"
        and chat_config.api_key
        else NullVisionExtractor()
    )

    chunk_repository = ChunkRepository(session)
    file_repository = FileRepository(session)
    memory_repository = MemoryRepository(session)
    summary_repository = SummaryRepository(session)
    tree_repository = TreeRepository(session)
    indexer = IndexerService(chunk_repository, embedder)

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
    file_service = FileService(
        file_repository=file_repository,
        tree_repository=tree_repository,
        chunk_repository=chunk_repository,
        indexer=indexer,
        storage=storage,
        cache=cache,
        text_generator=text_generator,
        vision_extractor=vision_extractor,
        target_chars=settings.chunk_target_chars,
        overlap_chars=settings.chunk_overlap_chars,
        max_chunks=settings.max_chunks_per_file,
        max_upload_bytes=settings.max_upload_bytes,
        max_text_bytes=settings.max_text_bytes,
        vision_max_pages=settings.vision_max_pages,
        pdf_text_threshold=settings.pdf_text_threshold,
    )
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
    return _services(request, session)[0]


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
