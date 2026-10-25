"""Composition root for the frequently used prompt slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session
from app.module.prompt.protocol.frequent_prompt_cache_protocol import (
    FrequentPromptCacheProtocol,
)
from app.module.prompt.repository.frequent_prompt_repository import (
    FrequentlyUsedPromptRepository,
)
from app.module.prompt.service.frequent_prompt_service import (
    FREQUENT_PROMPT_CACHE_TTL_SECONDS,
    FrequentlyUsedPromptService,
)


def get_prompt_cache(request: Request) -> FrequentPromptCacheProtocol:
    """Return the app-wide cache with scoped version support."""
    return cast(FrequentPromptCacheProtocol, request.app.state.cache)


def get_frequent_prompt_service(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    cache: FrequentPromptCacheProtocol = Depends(get_prompt_cache),  # noqa: B008
) -> FrequentlyUsedPromptService:
    """Build the CRUD service on the request transaction and shared cache."""
    return FrequentlyUsedPromptService(
        repository=FrequentlyUsedPromptRepository(session),
        cache=cache,
        cache_ttl_seconds=FREQUENT_PROMPT_CACHE_TTL_SECONDS,
    )


__all__ = ["get_frequent_prompt_service", "get_prompt_cache"]
