"""Composition root for the persistent agent slice.

Every request-scoped service is bound to the authenticated account here. The run
loop and tool calls open their own short-lived owner-scoped sessions, so an SSE
response never holds a request-scoped database session for the lifetime of the
stream and never inherits another account's RLS context.

Global runtime configuration and the system prompt are deployment-level data.
They are read through system-scoped sessions and written only by the root-guarded
settings routers; they never carry a ``user_id``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, replace
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.dependency.auth import (
    require_authenticated,
    require_root,
    require_stateless_authenticated,
)
from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.ai.model_catalog import MODEL_CATALOG, TIER_ORDER, spec_for
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.user_models import (
    ChatAssignment,
    UserGenerator,
    build_user_text_generator,
    load_assignment,
    resolve_endpoint,
    slot_values,
)
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database, get_db_session
from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.domain.companion_persona_domain import CompanionPersona
from app.module.agent.domain.user_profile_domain import UserProfile, UserProfileCard
from app.module.agent.protocol.chat_attachment_service_protocol import (
    ChatAttachmentServiceProtocol,
)
from app.module.agent.protocol.chat_attachment_storage_protocol import (
    ChatAttachmentStorageProtocol,
)
from app.module.agent.protocol.chat_generator_protocol import ChatGeneratorProtocol
from app.module.agent.protocol.companion_protocol import (
    CompanionContextContributorProtocol,
    CompanionIdentity,
    CompanionOwnMemoriesProtocol,
    CompanionPersonaLoaderProtocol,
    ContextContribution,
    ContextSignal,
    OwnMemory,
    RelationshipFacts,
)
from app.module.agent.protocol.system_prompt_cache_protocol import (
    SystemPromptCacheProtocol,
)
from app.module.agent.protocol.tool_service_protocol import (
    AgentToolServices,
    ToolServiceScopeProtocol,
)
from app.module.agent.repository.agent_config_repository import AgentConfigRepository
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.repository.chat_attachment_repository import (
    ChatAttachmentRepository,
)
from app.module.agent.repository.companion_context_repository import (
    CompanionContextRepository,
)
from app.module.agent.repository.saved_question_repository import SavedQuestionRepository
from app.module.agent.repository.system_prompt_repository import SystemPromptRepository
from app.module.agent.repository.web_source_repository import WebSourceRepository
from app.module.agent.service.agent_service import AgentService
from app.module.agent.service.agent_settings_service import AgentSettingsService
from app.module.agent.service.chat_attachment_service import ChatAttachmentService
from app.module.agent.service.history_message_service import AgentHistoryMessageService
from app.module.agent.service.saved_question_service import SavedQuestionService
from app.module.agent.service.system_prompt_service import SystemPromptService
from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.auth.dependencies import get_auth_service
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.auth_service import AuthService
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.companion.dependencies import (
    build_companion_context_contributor,
    build_companion_story_service,
    build_lore_recall,
    build_story_config_provider,
    record_companion_run,
)
from app.module.companion.domain.story_domain import (
    Relationship,
    normalize_locale,
    render_persona_section,
)
from app.module.companion.service.companion_context_contributor import (
    CompanionContextContributor,
)
from app.module.companion.service.lore_recall import CompanionLoreRecall
from app.module.knowledge.dependencies import (
    build_file_service,
    build_memory_service,
    build_search_service,
    build_timeline_service,
)
from app.module.knowledge.domain.provider_runtime_domain import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.web_research.dependencies import get_web_research_service

logger = logging.getLogger(__name__)


async def get_current_user_profile(
    user: UserSchema = Depends(require_authenticated),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserProfile:
    """Load the acting account's display name and card list for a new conversation."""
    profile = await auth_service.get_profile(user.user_id)
    return UserProfile(
        # Only an explicitly chosen display name enters the prompt. The login
        # username remains a UI fallback and does not leak into every system
        # prompt before the user has filled in the profile.
        display_name=user.display_name,
        cards=tuple(
            UserProfileCard(title=card.title, content=card.content) for card in profile.cards
        ),
    )


async def get_chat_assignment(
    request: Request,
    user: UserSchema = Depends(require_stateless_authenticated),
) -> ChatAssignment | None:
    """Load both endpoint assignments in one short system session.

    ``app_user`` is an auth table outside RLS, so the read works without an
    owner-scoped private session. ``None`` means the
    ``app.state.agent_chat_generator`` test seam is active: the override
    replaces assignment resolution entirely, so no assignment row is required
    and the fake is never replaced by escalation. FastAPI caches this
    dependency per request, so the service and the model plan share one read.
    """
    if getattr(request.app.state, "agent_chat_generator", None) is not None:
        return None
    database = cast(Database, request.app.state.db)
    async with database.system_session() as session:
        return await load_assignment(session, user.user_id)


async def get_user_generator(
    request: Request,
    assignment: ChatAssignment | None = Depends(get_chat_assignment),
) -> UserGenerator:
    """Build the caller's primary-slot generator once per request.

    A test override wins before the assignment is consulted. Otherwise the
    generator is built from the assigned primary endpoint row only; a missing,
    inactive, or keyless endpoint yields ``NullTextGenerator`` and the service
    turns that into ``model_not_assigned`` or ``provider_inactive`` before the
    SSE response starts.
    """
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    if assignment is None:
        override = getattr(request.app.state, "agent_chat_generator", None)
        assert override is not None
        # Test seam only: the conversation metadata keeps using the runtime
        # default so existing mechanics tests do not need assignment rows.
        chat_config = runtime.chat_config
        return UserGenerator(
            generator=cast(TextGeneratorProtocol, override),
            model=chat_config.model or "deepseek-flash",
            provider=chat_config.provider,
            effort=None,
            provider_config_id=None,
        )
    return build_user_text_generator(runtime, assignment, slot="primary")


def get_agent_chat_generator(
    generator: UserGenerator = Depends(get_user_generator),
) -> ChatGeneratorProtocol:
    """Return the resolved primary generator (or the test override)."""
    return cast(ChatGeneratorProtocol, generator.generator)


@dataclass(frozen=True)
class AgentModelPlan:
    """The primary endpoint plus its optional one-step escalation target.

    Every generator is built from the **same** endpoint row with a different
    model string, so escalation never changes keys, base URL, or provider. The
    plan is ``None`` for an unknown or top-tier model, which pins the account.
    """

    runtime: AiRuntime
    endpoint: ProviderConfig
    effort: str | None
    primary_model: str
    escalation_model: str

    def next_model(self, current_model: str) -> str | None:
        """Return the one allowed target, or ``None`` once already escalated."""
        if current_model != self.primary_model:
            return None
        return self.escalation_model

    def generator_for(self, model: str) -> ChatGeneratorProtocol:
        """Build the escalated client on the same endpoint row."""
        config = self.endpoint.model_copy(
            update={"model": model, "reasoning_effort": self.effort}
        )
        return cast(ChatGeneratorProtocol, self.runtime.builder.build_text_generator(config))


def _next_escalation_model(primary_model: str, provider: str) -> str | None:
    """Return the nearest higher catalog tier served by the same row provider.

    Unknown models and top-tier models have no target. A tier with no catalog
    row for the endpoint's provider is skipped rather than crossing provider
    families, because the row holds exactly one key and base URL.
    """
    spec = spec_for(primary_model)
    if spec is None or spec.tier is None:
        return None
    for tier in TIER_ORDER[TIER_ORDER.index(spec.tier) + 1 :]:
        match = next(
            (
                candidate.model
                for candidate in MODEL_CATALOG.values()
                if candidate.tier == tier and candidate.provider == provider
            ),
            None,
        )
        if match is not None:
            return match
    return None


def get_agent_model_plan(
    request: Request,
    assignment: ChatAssignment | None = Depends(get_chat_assignment),
    generator: UserGenerator = Depends(get_user_generator),
) -> AgentModelPlan | None:
    """Build the escalation plan for a catalog-known, usable primary slot.

    The plan is absent for the test seam, an unassigned or broken slot, an
    unknown model, and a primary already at the top tier. In every one of those
    cases the model is pinned and no escalation is attempted.
    """
    if (
        assignment is None
        or generator.provider == "none"
        or generator.provider_config_id is None
        or not generator.model
    ):
        return None
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    resolved = resolve_endpoint(runtime.chat_chain, generator.provider_config_id)
    if (
        resolved is None
        or not resolved.enabled
        or resolved.provider == "none"
        or not resolved.api_key
    ):
        return None
    escalation_model = _next_escalation_model(generator.model, resolved.provider)
    if escalation_model is None:
        return None
    return AgentModelPlan(
        runtime=runtime,
        endpoint=resolved,
        effort=slot_values(assignment, "primary").effort,
        primary_model=generator.model,
        escalation_model=escalation_model,
    )


def with_account_limits(
    base: AgentRuntimeConfig,
    assignment: ChatAssignment,
) -> tuple[AgentRuntimeConfig, str | None]:
    """Apply the account's stored window/threshold over the global snapshot.

    ``dataclasses.replace`` re-runs ``__post_init__``, so an inherited pair that
    became invalid after a global default change is rejected rather than
    silently shrunk. The caller logs the degradation and keeps the global
    snapshot; the assignment read surface reports ``invalid_threshold``.
    """
    window = assignment.context_window_tokens or base.context_window_tokens
    threshold = (
        assignment.compaction_threshold_tokens or base.compaction_threshold_tokens
    )
    if (
        window == base.context_window_tokens
        and threshold == base.compaction_threshold_tokens
    ):
        return base, None
    try:
        return (
            replace(
                base,
                context_window_tokens=window,
                compaction_threshold_tokens=threshold,
            ),
            None,
        )
    except ValueError:
        logger.warning(
            "invalid account agent limits user_id=%s; using the global snapshot",
            assignment.user_id,
        )
        return base, "invalid_threshold"


class _ToolServiceScope:
    """Open one owner-scoped database session and its services for one tool call.

    The account is captured when the scope is built, so a tool can never fall
    back to another user's RLS context. Every knowledge service is constructed
    with that ``user_id``; RLS remains the defense-in-depth boundary.
    """

    def __init__(self, request: Request, *, user_id: int, role: str) -> None:
        self.request = request
        self.database = cast(Database, request.app.state.db)
        self.user_id = user_id
        self.role = role

    def __call__(self) -> AbstractAsyncContextManager[AgentToolServices]:
        return self._scope()

    def _conversation_id(self) -> int | None:
        raw = self.request.path_params.get("conversation_id")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def _companion_context(
        self,
        session: AsyncSession,
    ) -> CompanionContextContributorProtocol | None:
        """Bind the context contributor to the companion frozen in this conversation."""
        conversation_id = self._conversation_id()
        if conversation_id is None:
            return None
        return await _conversation_contributor(
            self.request.app.state,
            session,
            user_id=self.user_id,
            conversation_id=conversation_id,
            quota=AccountQuotaService(self.database, self.user_id),
        )

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[AgentToolServices]:
        async with self.database.user_session(self.user_id, self.role) as session:
            state = self.request.app.state
            companion_context = await self._companion_context(session)
            conversation_id = self._conversation_id()
            companion_memories = (
                await _conversation_own_memories(
                    state,
                    session,
                    user_id=self.user_id,
                    conversation_id=conversation_id,
                    quota=AccountQuotaService(self.database, self.user_id),
                )
                if conversation_id is not None
                else None
            )
            services = AgentToolServices(
                search_service=build_search_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                file_service=await build_file_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                memory_service=await build_memory_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                timeline_service=build_timeline_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                history_service=AgentHistoryMessageService(
                    database=self.database,
                    user_id=self.user_id,
                    role=self.role,
                ),
                # Cross-module dependencies are only allowed in this assembly
                # root: the agent tool layer only sees
                # WebResearchServiceProtocol, and the web_research slice builds
                # the concrete implementation from app.state.ai_runtime (it opens
                # no database session).
                web_research_service=get_web_research_service(
                    self.request,
                    user_id=self.user_id,
                ),
                companion_context=companion_context,
                companion_memories=companion_memories,
                web_sources=(
                    WebSourceRepository(session, self.user_id, conversation_id)
                    if conversation_id is not None
                    else None
                ),
            )
            yield services


async def _conversation_contributor(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
    quota: AccountQuotaService | None = None,
) -> CompanionContextContributorProtocol | None:
    """Return the contributor for the companion frozen in one conversation."""
    frozen = await CompanionContextRepository(
        session,
        user_id,
    ).conversation_companion(conversation_id)
    if frozen is None:
        return None
    companion_ref, locale = frozen
    return _ContextContributorAdapter(
        build_companion_context_contributor(
            state,
            session,
            user_id=user_id,
            companion_ref=companion_ref,
            locale=normalize_locale(locale),
            quota=quota,
        )
    )


class _OwnMemoriesAdapter:
    """Map the companion slice's lore recall onto the agent's own-memories port."""

    def __init__(self, recall: CompanionLoreRecall, identity: CompanionIdentity) -> None:
        self.recall = recall
        self.identity = identity

    async def search_own(self, query: str, *, limit: int) -> list[OwnMemory]:
        return [
            OwnMemory(id=item.id, weight=item.weight, text=item.text)
            for item in await self.recall.search_own(query, limit=limit)
        ]

    async def relationship(self) -> RelationshipFacts | None:
        return _relationship_facts(await self.recall.relationship())

    async def guidance(self) -> str:
        return await self.recall.guidance()


async def _conversation_own_memories(
    state: State,
    session: AsyncSession,
    *,
    user_id: int,
    conversation_id: int,
    quota: AccountQuotaService | None = None,
) -> CompanionOwnMemoriesProtocol | None:
    """Return the frozen companion's own memories for ``recall_my_memories``."""
    identity = await CompanionContextRepository(
        session,
        user_id,
    ).conversation_identity(conversation_id)
    if identity is None:
        return None
    ref, name, locale = identity
    recall = build_lore_recall(
        state,
        session,
        user_id=user_id,
        companion_ref=ref,
        locale=normalize_locale(locale),
        quota=quota,
    )
    return _OwnMemoriesAdapter(recall, CompanionIdentity(ref=ref, name=name or ref))


class _ContextContributorAdapter:
    """Map the agent's context signal onto the companion slice's contributor."""

    def __init__(self, contributor: CompanionContextContributor) -> None:
        self.contributor = contributor

    async def contribute(self, signal: ContextSignal) -> list[ContextContribution]:
        recalled = await self.contributor.contribute(
            site=signal.site,
            text=signal.text,
            query=signal.query,
            offered=signal.offered_this_run,
        )
        if not recalled:
            return []
        facts = _relationship_facts(await self.contributor.relationship())
        return [
            ContextContribution(
                id=item.id,
                weight=item.weight,
                text=item.text,
                moment=item.moment,
                guidance=item.guidance,
                relationship=facts,
            )
            for item in recalled
        ]


def _relationship_facts(value: Relationship | None) -> RelationshipFacts | None:
    """Map the companion slice's relationship onto the agent's plain facts."""
    if value is None:
        return None
    return RelationshipFacts(
        first_met=value.first_met_at.date().isoformat() if value.first_met_at else None,
        days_known=value.days_known,
        conversations=value.conversations,
    )


class _MessageContextContributor:
    """Offer companion memories for a new message in a short owner session."""

    def __init__(self, database: Database, state: State, *, user_id: int, role: str) -> None:
        self.database = database
        self.state = state
        self.user_id = user_id
        self.role = role

    async def contribute(self, signal: ContextSignal) -> list[ContextContribution]:
        async with self.database.user_session(self.user_id, self.role) as session:
            contributor = await _conversation_contributor(
                self.state,
                session,
                user_id=self.user_id,
                conversation_id=signal.conversation_id,
                quota=AccountQuotaService(self.database, self.user_id),
            )
            if contributor is None:
                return []
            return await contributor.contribute(signal)


class _CompanionPersonaLoader:
    """Resolve the active companion persona in a short owner session."""

    def __init__(self, database: Database, state: State, *, user_id: int, role: str) -> None:
        self.database = database
        self.state = state
        self.user_id = user_id
        self.role = role

    async def __call__(self, locale: str | None) -> CompanionPersona | None:
        story_locale = normalize_locale(locale)
        async with self.database.user_session(self.user_id, self.role) as session:
            active = await build_companion_story_service(
                session,
                user_id=self.user_id,
                state=self.state,
            ).active_companion(story_locale)
        if active is None:
            return None
        return CompanionPersona(
            ref=active.ref,
            name=active.name,
            locale=active.locale,
            content=render_persona_section(
                active.persona,
                await build_story_config_provider(self.state).load(self.user_id),
            ),
        )


class _CompanionHandoff:
    """Resolve a conversation's current companion and the account's choice."""

    def __init__(self, database: Database, state: State, *, user_id: int, role: str) -> None:
        self.database = database
        self.state = state
        self.user_id = user_id
        self.role = role
        self.loader = _CompanionPersonaLoader(database, state, user_id=user_id, role=role)

    async def current(self, conversation_id: int) -> dict[str, str] | None:
        async with self.database.user_session(self.user_id, self.role) as session:
            return await CompanionContextRepository(session, self.user_id).current(
                conversation_id
            )

    async def active(self, locale: str | None) -> CompanionPersona | None:
        return await self.loader(locale)


class _CompanionRunObserver:
    """Count completed runs toward the conversation companion's bond."""

    def __init__(self, database: Database, state: State, *, user_id: int, role: str) -> None:
        self.database = database
        self.state = state
        self.user_id = user_id
        self.role = role

    async def run_completed(self, conversation_id: int) -> None:
        async with self.database.user_session(self.user_id, self.role) as session:
            frozen = await CompanionContextRepository(
                session,
                self.user_id,
            ).conversation_companion(conversation_id)
            if frozen is None:
                return
            companion_ref, locale = frozen
            await record_companion_run(
                self.state,
                session,
                user_id=self.user_id,
                companion_ref=companion_ref,
                locale=locale,
                conversation_id=conversation_id,
            )


def get_companion_persona_loader(
    request: Request,
    user: UserSchema = Depends(require_authenticated),
) -> CompanionPersonaLoaderProtocol:
    """Return the loader that freezes the active companion into a new conversation."""
    database = cast(Database, request.app.state.db)
    return _CompanionPersonaLoader(
        database,
        request.app.state,
        user_id=user.user_id,
        role=user.role,
    )


async def load_agent_runtime_config(database: Database) -> AgentRuntimeConfig:
    """Load one immutable global config snapshot in a short-lived session.

    The configuration table is global, so the read uses the system scope rather
    than an owner scope. Both HTTP dependencies and the background cleanup loop
    use this loader.
    """
    async with database.system_session() as session:
        service = AgentSettingsService(AgentConfigRepository(session))
        return await service.get_runtime_config()


async def get_agent_runtime_config(request: Request) -> AgentRuntimeConfig:
    """Load one immutable global config snapshot before a request proceeds.

    This dependency deliberately does not use the request-scoped session: the
    snapshot is read and committed before an SSE response starts, so no database
    connection is held for the lifetime of the stream.
    """
    database = cast(Database, request.app.state.db)
    return await load_agent_runtime_config(database)


def get_system_prompt_service(request: Request) -> SystemPromptService:
    """Build the global section service on the app cache and system sessions.

    The cache is injected through the agent slice's own
    ``SystemPromptCacheProtocol`` so the service never imports another slice's
    protocol. The version scope is managed by the service; this only wires
    ``app.state.cache`` in. Reads are global; writes are only reachable from the
    root-guarded system-prompt router.
    """
    database = cast(Database, request.app.state.db)
    cache = cast(SystemPromptCacheProtocol, request.app.state.cache)
    return SystemPromptService(
        repository=SystemPromptRepository(database),
        cache=cache,
    )


def get_system_prompt_admin_service(
    _root: UserSchema = Depends(require_root),
    service: SystemPromptService = Depends(get_system_prompt_service),
) -> SystemPromptService:
    """Expose the global prompt service to the root-only admin surface."""
    return service


def get_app_settings(request: Request) -> Settings:
    """Expose the resolved application settings to agent HTTP adapters."""
    return cast(Settings, request.app.state.settings)


def get_chat_attachment_service(
    request: Request,
    user: UserSchema = Depends(require_stateless_authenticated),
) -> ChatAttachmentService:
    """Build the owner-bound temporary-image service.

    The repository owns short sessions, so both management routes and the SSE
    turn loop can use the same service without holding a request transaction.
    """
    settings = cast(Settings, request.app.state.settings)
    database = cast(Database, request.app.state.db)
    storage = cast(ChatAttachmentStorageProtocol, request.app.state.storage)
    return ChatAttachmentService(
        repository=ChatAttachmentRepository(
            database,
            user_id=user.user_id,
            role=user.role,
        ),
        storage=storage,
        max_upload_bytes=settings.chat_attachment_max_bytes,
        user_id=user.user_id,
    )


def get_history_message_service(
    request: Request,
    user: UserSchema = Depends(require_authenticated),
) -> AgentHistoryMessageService:
    """Build an owner-bound read-only service for one cited message.

    The service opens its own short owner-scoped session, so the HTTP route does
    not need the request-scoped database transaction.
    """
    return AgentHistoryMessageService(
        database=cast(Database, request.app.state.db),
        user_id=user.user_id,
        role=user.role,
    )


def get_agent_service(
    request: Request,
    user: UserSchema = Depends(require_stateless_authenticated),
    chat_generator: ChatGeneratorProtocol = Depends(get_agent_chat_generator),
    config: AgentRuntimeConfig = Depends(get_agent_runtime_config),
    chat_attachments: ChatAttachmentServiceProtocol = Depends(
        get_chat_attachment_service
    ),
    assignment: ChatAssignment | None = Depends(get_chat_assignment),
    user_generator: UserGenerator = Depends(get_user_generator),
    model_plan: AgentModelPlan | None = Depends(get_agent_model_plan),
) -> AgentService:
    """Build an owner-bound agent service for one authenticated request.

    The repository captures ``user_id``/``role``; every short transaction in the
    JSON request and the later SSE stream therefore runs with the same account's
    RLS context. A service instance is never reused for another account.

    Provider and model come from the account's assigned primary endpoint, never
    from ``runtime.chat_config``. The test seam keeps the historical
    runtime-default metadata so conversation mechanics tests do not need
    assignment rows.
    """
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    effective_config = config
    if assignment is None:
        chat_config = runtime.chat_config
        provider = chat_config.provider
        if provider not in {"deepseek", "openai-compatible", "anthropic"}:
            provider = "deepseek"
        model = chat_config.model or "deepseek-flash"
        active_provider = chat_config.provider
        model_status = "assigned"
    else:
        provider = user_generator.provider
        model = user_generator.model
        active_provider = user_generator.provider
        effective_config, degraded = with_account_limits(config, assignment)
        if degraded is not None:
            logger.warning(
                "agent account limits degraded user_id=%s reason=%s",
                assignment.user_id,
                degraded,
            )
        if isinstance(user_generator.generator, NullTextGenerator):
            values = slot_values(assignment, "primary")
            model_status = (
                "missing"
                if values.row_id is None or not values.model
                else "inactive"
            )
        else:
            model_status = "assigned"
    database = cast(Database, request.app.state.db)
    repository = AgentRepository(
        database,
        user_id=user.user_id,
        role=user.role,
    )
    tool_registry = AgentToolRegistry(
        _ToolServiceScope(request, user_id=user.user_id, role=user.role)
    )
    companion_observer = _CompanionRunObserver(
        database,
        request.app.state,
        user_id=user.user_id,
        role=user.role,
    )
    return AgentService(
        repository=repository,
        chat_generator=chat_generator,
        tool_registry=tool_registry,
        default_provider=provider,
        default_model=model,
        config=effective_config,
        system_prompt_service=get_system_prompt_service(request),
        chat_attachments=chat_attachments,
        server_timezone=cast(Settings, request.app.state.settings).timezone,
        active_provider=active_provider,
        model_plan=model_plan,
        model_status=model_status,
        web_search_provider=_available_web_provider(
            runtime.web_search_config,
            runtime.web_search_client,
        ),
        web_fetch_provider=_available_web_provider(
            runtime.web_fetch_config,
            runtime.web_fetch_client,
        ),
        quota=AccountQuotaService(database, user.user_id),
        companion_runs=companion_observer,
        companion_context=_MessageContextContributor(
            database,
            request.app.state,
            user_id=user.user_id,
            role=user.role,
        ),
        companion_handoff=_CompanionHandoff(
            database,
            request.app.state,
            user_id=user.user_id,
            role=user.role,
        ),
    )


def _available_web_provider(
    config: ProviderConfig,
    client: object | None = None,
) -> str:
    """Return a web provider only when it is active and has a usable credential.

    ``client`` is the runtime client, which may be a fallback wrapper whose
    aggregate ``configured`` is true because a backup holds the key even though
    the primary row does not. The client is deliberately typed loosely: the
    agent slice does not import the knowledge web-client protocol here.
    """
    configured = getattr(client, "configured", None) if client is not None else None
    has_credentials = bool(config.api_key) if configured is None else bool(configured)
    if (
        config.enabled
        and has_credentials
        and config.provider in {"tavily", "exa", "deepseek"}
    ):
        return config.provider
    return "none"


def get_agent_settings_service(
    _root: UserSchema = Depends(require_root),
    session: AsyncSession = Depends(get_db_session),
) -> AgentSettingsService:
    """Build root-only settings CRUD on the request transaction; never used for SSE."""
    return AgentSettingsService(AgentConfigRepository(session))


def get_saved_question_service(
    user: UserSchema = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
) -> SavedQuestionService:
    """Build owner-scoped saved-question CRUD on the request transaction.

    CRUD deliberately does not resolve the chat generator, so questions can be
    captured and edited while the AI provider is not configured.
    """
    return SavedQuestionService(
        repository=SavedQuestionRepository(session, user_id=user.user_id)
    )


def get_saved_question_ask_service(
    user: UserSchema = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
    agent_service: AgentService = Depends(get_agent_service),
) -> SavedQuestionService:
    """Build the ask orchestrator; a missing provider raises the existing 503.

    ``ask`` is a regular JSON request, so holding the request session while the
    agent runs does not hold a connection for an SSE stream. Both the saved-question
    repository and the agent service are bound to the acting account.
    """
    return SavedQuestionService(
        repository=SavedQuestionRepository(session, user_id=user.user_id),
        agent_service=agent_service,
    )


__all__ = [
    "AgentModelPlan",
    "ToolServiceScopeProtocol",
    "get_agent_chat_generator",
    "get_agent_model_plan",
    "get_agent_runtime_config",
    "get_agent_service",
    "get_agent_settings_service",
    "get_app_settings",
    "get_chat_assignment",
    "get_chat_attachment_service",
    "get_current_user_profile",
    "get_history_message_service",
    "get_saved_question_ask_service",
    "get_saved_question_service",
    "get_system_prompt_admin_service",
    "get_user_generator",
    "load_agent_runtime_config",
    "with_account_limits",
]
