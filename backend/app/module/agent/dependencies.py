"""Composition root for the persistent agent slice.

Every request-scoped service is bound to the authenticated account here. The run
loop and tool calls open their own short-lived owner-scoped sessions, so an SSE
response never holds a request-scoped database session for the lifetime of the
stream and never inherits another account's RLS context.

Global runtime configuration and the system prompt are deployment-level data.
They are read through system-scoped sessions and written only by the root-guarded
settings routers; they never carry a ``user_id``.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependency.auth import (
    require_authenticated,
    require_root,
    require_stateless_authenticated,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database, get_db_session
from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.domain.user_profile_domain import UserProfile, UserProfileCard
from app.module.agent.exception.domain_error import AgentNotConfiguredError
from app.module.agent.protocol.chat_generator_protocol import ChatGeneratorProtocol
from app.module.agent.protocol.system_prompt_cache_protocol import (
    SystemPromptCacheProtocol,
)
from app.module.agent.protocol.tool_service_protocol import (
    AgentToolServices,
    ToolServiceScopeProtocol,
)
from app.module.agent.repository.agent_config_repository import AgentConfigRepository
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.repository.saved_question_repository import SavedQuestionRepository
from app.module.agent.repository.system_prompt_repository import SystemPromptRepository
from app.module.agent.service.agent_service import AgentService
from app.module.agent.service.agent_settings_service import AgentSettingsService
from app.module.agent.service.saved_question_service import SavedQuestionService
from app.module.agent.service.system_prompt_service import SystemPromptService
from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.auth.dependencies import get_auth_service
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.auth_service import AuthService
from app.module.knowledge.dependencies import (
    build_file_service,
    build_memory_service,
    build_search_service,
    build_timeline_service,
)
from app.module.web_research.dependencies import get_web_research_service


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


def get_agent_chat_generator(request: Request) -> ChatGeneratorProtocol:
    """Resolve the chat generator, honouring a test/runtime override.

    Tests can either override this dependency or set
    ``app.state.agent_chat_generator`` to a deterministic fake.
    """
    override = getattr(request.app.state, "agent_chat_generator", None)
    if override is not None:
        return cast(ChatGeneratorProtocol, override)
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    generator = runtime.text_generator
    if not hasattr(generator, "complete_chat"):
        raise AgentNotConfiguredError()
    return cast(ChatGeneratorProtocol, generator)


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

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[AgentToolServices]:
        async with self.database.user_session(self.user_id, self.role) as session:
            state = self.request.app.state
            services = AgentToolServices(
                search_service=build_search_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                file_service=build_file_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                memory_service=build_memory_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                timeline_service=build_timeline_service(
                    state,
                    session,
                    user_id=self.user_id,
                ),
                # 跨模組依賴只允許出現在這個組裝根：agent 工具層只看
                # WebResearchServiceProtocol，實際實作由 web_research slice
                # 從 app.state.ai_runtime 組裝（它不開資料庫 session）。
                web_research_service=get_web_research_service(self.request),
            )
            yield services


async def get_agent_runtime_config(request: Request) -> AgentRuntimeConfig:
    """Load one immutable global config snapshot in a short-lived session.

    This dependency deliberately does not use the request-scoped session: the
    snapshot is read and committed before an SSE response starts, so no database
    connection is held for the lifetime of the stream. The configuration table is
    global, so the read uses the system scope rather than an owner scope.
    """
    database = cast(Database, request.app.state.db)
    async with database.system_session() as session:
        service = AgentSettingsService(AgentConfigRepository(session))
        config = await service.get_runtime_config()
    return config


def get_system_prompt_service(request: Request) -> SystemPromptService:
    """Build the global section service on the app cache and system sessions.

    The cache is injected through the agent slice's own
    ``SystemPromptCacheProtocol`` so the service never imports another slice's
    protocol. 版本 scope 由 service 管理，這裡只負責把 ``app.state.cache``
    接進來。Reads are global; writes are only reachable from the root-guarded
    system-prompt router.
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


def get_agent_service(
    request: Request,
    user: UserSchema = Depends(require_stateless_authenticated),
    chat_generator: ChatGeneratorProtocol = Depends(get_agent_chat_generator),
    config: AgentRuntimeConfig = Depends(get_agent_runtime_config),
) -> AgentService:
    """Build an owner-bound agent service for one authenticated request.

    The repository captures ``user_id``/``role``; every short transaction in the
    JSON request and the later SSE stream therefore runs with the same account's
    RLS context. A service instance is never reused for another account.
    """
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    chat_config = runtime.chat_config
    provider = chat_config.provider
    if provider not in {"deepseek", "openai-compatible"}:
        provider = "deepseek"
    model = chat_config.model or "deepseek-flash"
    database = cast(Database, request.app.state.db)
    repository = AgentRepository(
        database,
        user_id=user.user_id,
        role=user.role,
    )
    tool_registry = AgentToolRegistry(
        _ToolServiceScope(request, user_id=user.user_id, role=user.role)
    )
    return AgentService(
        repository=repository,
        chat_generator=chat_generator,
        tool_registry=tool_registry,
        default_provider=provider,
        default_model=model,
        config=config,
        system_prompt_service=get_system_prompt_service(request),
        server_timezone=cast(Settings, request.app.state.settings).timezone,
    )


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
    "ToolServiceScopeProtocol",
    "get_agent_chat_generator",
    "get_agent_runtime_config",
    "get_agent_service",
    "get_agent_settings_service",
    "get_current_user_profile",
    "get_saved_question_ask_service",
    "get_saved_question_service",
    "get_system_prompt_admin_service",
]
