"""Composition root for the chat companion slice.

Besides the HTTP dependencies, this module exposes plain builders that the
agent slice's composition root uses on its own owner-scoped sessions: the
story service (active persona and bond counting) and the lore recall.
"""

import logging
from collections.abc import Sequence
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.dependency.auth import require_authenticated
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.user_models import build_user_text_generator, load_assignment
from app.infrastructure.database.session import Database, get_db_session
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.companion.domain.life_story_domain import (
    FAIL_PROVIDER_REJECTED,
    FAIL_PROVIDER_UNAVAILABLE,
    SKIP_MODEL_NOT_ASSIGNED,
    SKIP_QUOTA,
    LifeStoryGenerationError,
    clip_text,
)
from app.module.companion.domain.story_domain import StoryLocale
from app.module.companion.protocol.companion_protocol import CompanionStorageProtocol
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionPolicyProviderProtocol,
    CompanionStoryConfigProviderProtocol,
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.protocol.life_story_protocol import (
    LifeStoryGeneration,
    LifeStoryMaterial,
    LifeStoryMaterialRequest,
    LifeStoryTextGeneratorProtocol,
)
from app.module.companion.repository.companion_life_story_repository import (
    LifeStoryJobQueue,
    LifeStoryRepository,
)
from app.module.companion.repository.companion_repository import CompanionRepository
from app.module.companion.repository.companion_story_repository import (
    CompanionStoryRepository,
)
from app.module.companion.service.companion_service import CompanionService
from app.module.companion.service.companion_story_service import CompanionStoryService
from app.module.companion.service.life_story_scheduler import LifeStoryScheduler
from app.module.companion.service.life_story_worker import LifeStoryWorker
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
from app.module.knowledge.dependencies import build_search_service
from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    ChatUsageLimitExceededError,
)
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.repository.memory_repository import MemoryRepository
from app.module.knowledge.service.metered_text_generator import MeteredTextGenerator

logger = logging.getLogger(__name__)


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
        generated=LifeStoryRepository(session, user_id),
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


# --- C: life stories ---------------------------------------------------------


class _LifeStoryGenerator:
    """Adapt the account's metered auxiliary generator to the life-story port.

    Provider and allowance errors become :class:`LifeStoryGenerationError`
    codes here, so the companion slice's services never import knowledge
    exceptions. The endpoint's completion cap bounds the call; the story is
    also clipped to ``max_chars`` after it returns.
    """

    def __init__(self, generator: TextGeneratorProtocol, provider_config_id: int | None) -> None:
        self.generator = generator
        self.provider_config_id = provider_config_id

    async def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, str]],
        max_output_tokens: int,
    ) -> LifeStoryGeneration:
        del max_output_tokens  # bounded by the endpoint's completion cap
        prompt = "\n\n".join(message.get("content", "") for message in messages)
        try:
            completion = await self.generator.complete_text(system, prompt)
        except ChatUsageLimitExceededError as exc:
            raise LifeStoryGenerationError(SKIP_QUOTA, skip=True) from exc
        except AiNotConfiguredError as exc:
            raise LifeStoryGenerationError(SKIP_MODEL_NOT_ASSIGNED, skip=True) from exc
        except AiProviderError as exc:
            if exc.retryable:
                raise LifeStoryGenerationError(
                    FAIL_PROVIDER_UNAVAILABLE,
                    retryable=True,
                ) from exc
            raise LifeStoryGenerationError(FAIL_PROVIDER_REJECTED) from exc
        usage = completion.usage or {}
        return LifeStoryGeneration(
            text=completion.text,
            model=completion.model or self.generator.model_name,
            provider_config_id=self.provider_config_id,
            prompt_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
            completion_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
        )


class _LifeStoryMaterialSelector:
    """Pick the owner's own memories (recent plus one themed search) and files.

    Runs on the owner's RLS session only. Deprecated and deleted memories are
    never offered; items used by earlier stories are skipped; every excerpt is
    clipped so the whole selection fits ``max_chars``.
    """

    def __init__(self, state: State, session: AsyncSession, user_id: int) -> None:
        self.state = state
        self.session = session
        self.user_id = user_id

    async def select(self, request: LifeStoryMaterialRequest) -> list[LifeStoryMaterial]:
        limit = max(1, request.limit)
        per_item = max(120, request.max_chars // limit)
        chosen: list[LifeStoryMaterial] = []
        seen_memories: set[int] = set(request.exclude_memory_ids)
        seen_files: set[int] = set(request.exclude_file_ids)
        recent = await MemoryRepository(self.session, self.user_id).list_recent(
            limit=limit * 3,
            offset=0,
        )
        for memory in recent:
            if len(chosen) >= max(1, (limit + 1) // 2):
                break
            if memory.status != "active" or memory.id in seen_memories:
                continue
            seen_memories.add(memory.id)
            chosen.append(
                LifeStoryMaterial(
                    kind="memory",
                    source_id=memory.id,
                    title=clip_text(memory.title, 80),
                    excerpt=clip_text(memory.content, per_item),
                )
            )
        query = " ".join(request.seed_themes).strip()
        if query and len(chosen) < limit:
            try:
                response = await build_search_service(
                    self.state,
                    self.session,
                    user_id=self.user_id,
                ).search(query[:200], result_number=limit, include_history=False)
            except Exception:
                logger.warning("life story material search failed user_id=%s", self.user_id)
            else:
                for hit in response.memory_results:
                    if len(chosen) >= limit:
                        break
                    if hit.status != "active" or hit.memory_id in seen_memories:
                        continue
                    seen_memories.add(hit.memory_id)
                    chosen.append(
                        LifeStoryMaterial(
                            kind="memory",
                            source_id=hit.memory_id,
                            title=clip_text(hit.title, 80),
                            excerpt=clip_text(hit.content, per_item),
                        )
                    )
                for file_hit in response.file_results:
                    if len(chosen) >= limit:
                        break
                    if not file_hit.is_current or file_hit.file_id in seen_files:
                        continue
                    seen_files.add(file_hit.file_id)
                    chosen.append(
                        LifeStoryMaterial(
                            kind="file",
                            source_id=file_hit.file_id,
                            title=clip_text(file_hit.file_name, 80),
                            excerpt=clip_text(file_hit.content, per_item),
                        )
                    )
        return chosen[:limit]


def build_life_story_scheduler(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
) -> LifeStoryScheduler:
    """Build the cadence scheduler on an owner-scoped session."""
    return LifeStoryScheduler(
        repository=LifeStoryRepository(session, user_id),
        config=build_story_config_provider(state),
        user_id=user_id,
    )


async def record_companion_run(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    companion_ref: str,
    locale: str,
    conversation_id: int,
) -> None:
    """Count one completed run, then the conversation, and queue a story if due."""
    await build_companion_story_service(session, user_id=user_id).record_completed_run(
        companion_ref
    )
    await build_life_story_scheduler(state, session, user_id=user_id).record_conversation(
        companion_ref,
        locale,
        conversation_id,
    )


def build_life_story_worker(state: State) -> LifeStoryWorker:
    """Build the dedicated worker's life-story loop."""
    database = cast(Database, state.db)

    async def generator(
        session: AsyncSession,
        user_id: int,
        max_output_tokens: int,
    ) -> LifeStoryTextGeneratorProtocol | None:
        del max_output_tokens
        runtime = cast(AiRuntime, state.ai_runtime)
        built = build_user_text_generator(
            runtime,
            await load_assignment(session, user_id),
            slot="auxiliary",
        )
        if built.provider == "none":
            return None
        quota = AccountQuotaService(database, user_id)
        return _LifeStoryGenerator(
            MeteredTextGenerator(built.generator, quota),
            built.provider_config_id,
        )

    async def chat_allowed(user_id: int) -> bool:
        return await AccountQuotaService(database, user_id).chat_allowed()

    return LifeStoryWorker(
        database=database,
        config=build_story_config_provider(state),
        content=build_content_provider(state),
        story_service=lambda session, user_id: build_companion_story_service(
            session,
            user_id=user_id,
        ),
        materials=lambda session, user_id: _LifeStoryMaterialSelector(state, session, user_id),
        generator=generator,
        chat_allowed=chat_allowed,
        repository=LifeStoryRepository,
        queue=LifeStoryJobQueue,
    )


__all__ = [
    "build_companion_story_service",
    "build_content_provider",
    "build_life_story_scheduler",
    "build_life_story_worker",
    "build_lore_recall",
    "build_lore_vector_warmer",
    "build_policy_provider",
    "build_story_config_provider",
    "get_companion_service",
    "get_companion_story_service",
    "record_companion_run",
]
