"""Composition root for the standalone media slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.vision_client import DeepSeekVisionCaptioner, NullMediaCaptioner
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import get_db_session
from app.module.media.protocol.media_cache_protocol import MediaCacheProtocol
from app.module.media.protocol.media_storage_protocol import MediaStorageProtocol
from app.module.media.repository.media_repository import MediaRepository
from app.module.media.service.media_service import MediaService


def get_media_ai_runtime(request: Request) -> AiRuntime:
    return cast(AiRuntime, request.app.state.ai_runtime)


def get_media_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_media_storage(request: Request) -> MediaStorageProtocol:
    return cast(MediaStorageProtocol, request.app.state.storage)


def get_media_cache(request: Request) -> MediaCacheProtocol:
    return cast(MediaCacheProtocol, request.app.state.cache)


def get_media_captioner(
    request: Request,
    ai_runtime: AiRuntime = Depends(get_media_ai_runtime),
    settings: Settings = Depends(get_media_settings),
) -> DeepSeekVisionCaptioner | NullMediaCaptioner:
    config = ai_runtime.chat_config
    if not config.enabled or config.provider == "none" or not config.api_key:
        return NullMediaCaptioner()
    return DeepSeekVisionCaptioner(
        api_key=config.api_key,
        base_url=config.base_url or settings.deepseek_base_url,
        model=config.model,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )


def get_media_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    captioner: DeepSeekVisionCaptioner | NullMediaCaptioner = Depends(get_media_captioner),
    settings: Settings = Depends(get_media_settings),
) -> MediaService:
    return MediaService(
        repository=MediaRepository(session),
        captioner=captioner,
        storage=get_media_storage(request),
        cache=get_media_cache(request),
        max_bytes=settings.max_upload_bytes,
    )
