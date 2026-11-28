"""Composition root for the chat companion slice.

Besides the HTTP dependencies, this module exposes plain builders that the
agent slice's composition root uses on its own owner-scoped sessions: the
story service (active persona and bond counting) and the lore recall.
"""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.dependency.auth import require_authenticated
from app.infrastructure.database.session import get_db_session
from app.module.auth.schema.auth_schema import UserSchema
from app.module.companion.domain.story_domain import StoryLocale
from app.module.companion.protocol.companion_protocol import CompanionStorageProtocol
from app.module.companion.protocol.companion_story_protocol import (
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.repository.companion_repository import CompanionRepository
from app.module.companion.repository.companion_story_repository import (
    CompanionStoryRepository,
)
from app.module.companion.service.companion_service import CompanionService
from app.module.companion.service.companion_story_service import CompanionStoryService
from app.module.companion.service.lore_recall import CompanionLoreRecall


def get_companion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
) -> CompanionService:
    """Build the owner-bound companion service on the request transaction."""
    return CompanionService(
        repository=CompanionRepository(session),
        storage=cast(CompanionStorageProtocol, request.app.state.storage),
        user_id=user.user_id,
        stories=CompanionStoryRepository(session, user.user_id),
    )


def build_companion_story_service(session: AsyncSession, *, user_id: int) -> CompanionStoryService:
    """Build the owner-bound story service on any owner-scoped session."""
    return CompanionStoryService(
        repository=CompanionStoryRepository(session, user_id),
        companions=CompanionRepository(session),
        user_id=user_id,
    )


def get_companion_story_service(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
) -> CompanionStoryService:
    """Build the story editor service on the request transaction."""
    return build_companion_story_service(session, user_id=user.user_id)


def build_lore_recall(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    companion_ref: str,
    locale: StoryLocale,
    quota: LoreEmbeddingQuotaProtocol | None = None,
) -> CompanionLoreRecall:
    """Build the lore recall for one tool call on the agent's owner session."""
    runtime = getattr(state, "ai_runtime", None)
    embedder = getattr(runtime, "embedder", None) if runtime is not None else None
    return CompanionLoreRecall(
        stories=build_companion_story_service(session, user_id=user_id),
        companion_ref=companion_ref,
        locale=locale,
        embedder=cast(LoreEmbedderProtocol | None, embedder),
        quota=quota,
    )


__all__ = [
    "build_companion_story_service",
    "build_lore_recall",
    "get_companion_service",
    "get_companion_story_service",
]
