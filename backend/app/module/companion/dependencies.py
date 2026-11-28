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
from app.infrastructure.database.session import Database, get_db_session
from app.module.auth.schema.auth_schema import UserSchema
from app.module.companion.domain.story_domain import StoryLocale
from app.module.companion.protocol.companion_protocol import CompanionStorageProtocol
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionPolicyProviderProtocol,
    CompanionStoryConfigProviderProtocol,
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.repository.companion_providers import (
    DbCompanionConfigProvider,
    DbCompanionContentProvider,
    DbCompanionPolicyProvider,
)
from app.module.companion.repository.companion_repository import CompanionRepository
from app.module.companion.repository.companion_story_repository import (
    CompanionStoryRepository,
)
from app.module.companion.service.companion_seeder import SeedResult, seed_companion_world
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


def get_companion_story_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
) -> CompanionStoryService:
    """Build the story editor service on the request transaction."""
    return build_companion_story_service(session, user_id=user.user_id, state=request.app.state)


def _state_embedder(state: State) -> LoreEmbedderProtocol | None:
    runtime = getattr(state, "ai_runtime", None)
    embedder = getattr(runtime, "embedder", None) if runtime is not None else None
    return cast(LoreEmbedderProtocol | None, embedder)


def _state_vectors(state: State) -> LoreVectorStore:
    cache = getattr(state, "cache", None)
    return LoreVectorStore(cast(LoreVectorCacheProtocol | None, cache))


# --- A: foundation ---------------------------------------------------------
#
# The live world (presets, lore, canon, world docs), the story configuration,
# and root's per-account policy are database-backed and root-editable. The
# seed files are applied by :func:`seed_companion` at process start. Each
# builder returns the provider installed on ``app.state`` (tests may install
# their own), else installs the database-backed one on first use, else (no
# database at all) serves the seed files.


def _state_database(state: State | None) -> Database | None:
    return cast(Database | None, getattr(state, "db", None)) if state is not None else None


def build_story_config_provider(state: State | None) -> CompanionStoryConfigProviderProtocol:
    """Return the live story config provider (``app.state.companion_story_config``)."""
    provider = getattr(state, "companion_story_config", None) if state is not None else None
    if provider is not None:
        return cast(CompanionStoryConfigProviderProtocol, provider)
    database = _state_database(state)
    if database is None:
        return StaticStoryConfigProvider()
    installed = DbCompanionConfigProvider(database, fallback=StaticStoryConfigProvider())
    assert state is not None
    state.companion_story_config = installed
    return installed


def build_content_provider(state: State | None) -> CompanionContentProviderProtocol:
    """Return the preset/lore/canon/world-doc provider (``app.state.companion_content``)."""
    provider = getattr(state, "companion_content", None) if state is not None else None
    if provider is not None:
        return cast(CompanionContentProviderProtocol, provider)
    database = _state_database(state)
    if database is None:
        return StaticCompanionContentProvider()
    installed = DbCompanionContentProvider(database, fallback=StaticCompanionContentProvider())
    assert state is not None
    state.companion_content = installed
    return installed


def build_policy_provider(state: State | None) -> CompanionPolicyProviderProtocol:
    """Return root's per-account companion policy provider (``app.state.companion_policy``)."""
    provider = getattr(state, "companion_policy", None) if state is not None else None
    if provider is not None:
        return cast(CompanionPolicyProviderProtocol, provider)
    database = _state_database(state)
    if database is None:
        return StaticCompanionPolicyProvider()
    installed = DbCompanionPolicyProvider(database)
    assert state is not None
    state.companion_policy = installed
    return installed


def install_companion_providers(state: State) -> None:
    """Install the database-backed providers on a process ``state``."""
    build_story_config_provider(state)
    build_content_provider(state)
    build_policy_provider(state)


async def seed_companion(state: State) -> SeedResult:
    """Apply the shipped seed bundle, then install the live providers."""
    database = _state_database(state)
    if database is None:
        return SeedResult()
    result = await seed_companion_world(database)
    install_companion_providers(state)
    content = getattr(state, "companion_content", None)
    if isinstance(content, DbCompanionContentProvider):
        content.invalidate()
    config = getattr(state, "companion_story_config", None)
    if isinstance(config, DbCompanionConfigProvider):
        config.invalidate()
    return result


def build_companion_story_service(
    session: AsyncSession,
    *,
    user_id: int,
    state: State | None = None,
) -> CompanionStoryService:
    """Build the owner-bound story service on any owner-scoped session."""
    return CompanionStoryService(
        repository=CompanionStoryRepository(session, user_id),
        companions=CompanionRepository(session),
        user_id=user_id,
        content=build_content_provider(state),
        config=build_story_config_provider(state),
        policy=build_policy_provider(state),
    )


def build_lore_vector_warmer(state: State) -> LoreVectorWarmer:
    """Build the worker loop that embeds shipped preset lore ahead of time."""
    return LoreVectorWarmer(
        embedder=lambda: _state_embedder(state),
        vectors=_state_vectors(state),
        content=lambda: build_content_provider(state),
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
        stories=build_companion_story_service(session, user_id=user_id, state=state),
        companion_ref=companion_ref,
        locale=locale,
        embedder=_state_embedder(state),
        quota=quota,
        vectors=_state_vectors(state),
        config=build_story_config_provider(state),
    )


__all__ = [
    "build_companion_story_service",
    "build_content_provider",
    "build_lore_recall",
    "build_lore_vector_warmer",
    "build_policy_provider",
    "build_story_config_provider",
    "get_companion_service",
    "get_companion_story_service",
    "install_companion_providers",
    "seed_companion",
]
