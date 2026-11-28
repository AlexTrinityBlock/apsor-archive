"""Composition root for the chat companion slice.

Besides the HTTP dependencies, this module exposes plain builders that the
agent slice's composition root uses on its own owner-scoped sessions: the
story service (active persona and bond counting) and the lore recall.
"""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.dependency.auth import require_authenticated, require_root
from app.infrastructure.database.session import (
    ADMIN_SCOPE_COMPANION,
    apply_admin_scope,
    get_db_session,
)
from app.module.auth.schema.auth_schema import UserSchema
from app.module.companion.domain.story_domain import StoryLocale
from app.module.companion.protocol.companion_admin_protocol import CompanionSeederProtocol
from app.module.companion.protocol.companion_protocol import CompanionStorageProtocol
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionPolicyProviderProtocol,
    CompanionStoryConfigProviderProtocol,
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.repository.companion_admin_repository import CompanionAdminRepository
from app.module.companion.repository.companion_repository import CompanionRepository
from app.module.companion.repository.companion_story_repository import (
    CompanionStoryRepository,
)
from app.module.companion.service.companion_admin_service import (
    CompanionAdminService,
    CompanionCatalogService,
)
from app.module.companion.service.companion_service import CompanionService
from app.module.companion.service.companion_story_service import CompanionStoryService
from app.module.companion.service.lore_recall import CompanionLoreRecall
from app.module.companion.service.lore_vectors import (
    LoreVectorCacheProtocol,
    LoreVectorStore,
    LoreVectorWarmer,
)
from app.module.companion.service.story_config import (
    StaticCompanionContentProvider,
    StaticCompanionPolicyProvider,
    StaticStoryConfigProvider,
)
from app.shared.time import utcnow


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


def _state_embedder(state: State) -> LoreEmbedderProtocol | None:
    runtime = getattr(state, "ai_runtime", None)
    embedder = getattr(runtime, "embedder", None) if runtime is not None else None
    return cast(LoreEmbedderProtocol | None, embedder)


def _state_vectors(state: State) -> LoreVectorStore:
    cache = getattr(state, "cache", None)
    return LoreVectorStore(cast(LoreVectorCacheProtocol | None, cache))


def build_story_config_provider(state: State) -> CompanionStoryConfigProviderProtocol:
    """Return the live story config provider (``app.state`` may install one).

    Root administration stores the live values; until a store is installed on
    ``app.state.companion_story_config``, the seed defaults are served.
    """
    provider = getattr(state, "companion_story_config", None)
    if provider is not None:
        return cast(CompanionStoryConfigProviderProtocol, provider)
    return StaticStoryConfigProvider()


def build_content_provider(state: State) -> CompanionContentProviderProtocol:
    """Return the preset/canon/world-doc provider (``app.state`` may install one).

    The database-backed provider is installed on ``app.state.companion_content``;
    until then the shipped seed files are served.
    """
    provider = getattr(state, "companion_content", None)
    if provider is not None:
        return cast(CompanionContentProviderProtocol, provider)
    return StaticCompanionContentProvider()


def build_policy_provider(state: State) -> CompanionPolicyProviderProtocol:
    """Return root's per-account companion policy provider.

    The database-backed provider is installed on ``app.state.companion_policy``;
    until then every account gets the unrestricted default.
    """
    provider = getattr(state, "companion_policy", None)
    if provider is not None:
        return cast(CompanionPolicyProviderProtocol, provider)
    return StaticCompanionPolicyProvider()


def build_lore_vector_warmer(state: State) -> LoreVectorWarmer:
    """Build the worker loop that embeds shipped preset lore ahead of time."""
    return LoreVectorWarmer(
        embedder=lambda: _state_embedder(state),
        vectors=_state_vectors(state),
    )


def build_lore_recall(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    companion_ref: str,
    locale: StoryLocale,
    quota: LoreEmbeddingQuotaProtocol | None = None,
) -> CompanionLoreRecall:
    """Build the lore recall for one call on the agent's owner session."""
    return CompanionLoreRecall(
        stories=build_companion_story_service(session, user_id=user_id),
        companion_ref=companion_ref,
        locale=locale,
        embedder=_state_embedder(state),
        quota=quota,
        vectors=_state_vectors(state),
        config=build_story_config_provider(state),
    )


# --- D: admin ---------------------------------------------------------------


async def get_companion_admin_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_root),  # noqa: B008
) -> CompanionAdminService:
    """Build root's companion admin service on an admin-scoped request transaction.

    ``require_root`` rejects normal accounts and impersonated sessions (they carry
    the target's role). The companion admin scope then lets RLS expose companion
    tables across accounts for this transaction only; archive tables stay owner-only.
    """
    await apply_admin_scope(session, ADMIN_SCOPE_COMPANION)
    state = request.app.state
    seeder = getattr(state, "companion_seeder", None)
    return CompanionAdminService(
        CompanionAdminRepository(session),
        actor_user_id=user.user_id,
        seeder=cast(CompanionSeederProtocol | None, seeder),
        clock=utcnow,
        invalidate=lambda user_id: _invalidate_providers(state, user_id),
    )


_CACHED_PROVIDERS = ("companion_story_config", "companion_content", "companion_policy")


def _invalidate_providers(state: State, user_id: int | None) -> None:
    """Drop cached config, content, and policy after a root write.

    Database-backed providers installed on ``app.state`` expose ``invalidate``;
    the static seed providers do not, so they are skipped.
    """
    for name in _CACHED_PROVIDERS:
        provider = getattr(state, name, None)
        invalidate = getattr(provider, "invalidate", None)
        if callable(invalidate):
            invalidate(user_id)


def get_companion_catalog_service(
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
) -> CompanionCatalogService:
    """Build the account's preset catalog on its own owner-scoped transaction."""
    return CompanionCatalogService(CompanionAdminRepository(session), user_id=user.user_id)


__all__ = [
    "build_companion_story_service",
    "build_content_provider",
    "build_lore_recall",
    "build_lore_vector_warmer",
    "build_policy_provider",
    "build_story_config_provider",
    "get_companion_admin_service",
    "get_companion_catalog_service",
    "get_companion_service",
    "get_companion_story_service",
]
