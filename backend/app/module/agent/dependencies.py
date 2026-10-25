"""Composition root for the persistent agent slice.

The run loop opens its own short-lived sessions through the application's session
factory. Tool calls use a separate short-lived scope so an SSE response never
holds a request-scoped database session for the lifetime of the stream.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database, get_db_session
from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.exception.domain_error import AgentNotConfiguredError
from app.module.agent.protocol.chat_generator_protocol import ChatGeneratorProtocol
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
from app.module.knowledge.dependencies import (
    get_file_service,
    get_memory_service,
    get_search_service,
    get_timeline_service,
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
    """Open one database session and its services for one tool call."""

    def __init__(self, request: Request) -> None:
        self.request = request
        self.session_factory = request.app.state.db.session_factory

    def __call__(self) -> AbstractAsyncContextManager[AgentToolServices]:
        return self._scope()

    @asynccontextmanager
    async def _scope(self) -> AsyncIterator[AgentToolServices]:
        async with self.session_factory() as session:
            try:
                services = AgentToolServices(
                    search_service=get_search_service(self.request, session),
                    file_service=get_file_service(self.request, session),
                    memory_service=get_memory_service(self.request, session),
                    timeline_service=get_timeline_service(self.request, session),
                )
                yield services
                await session.commit()
            except Exception:
                await session.rollback()
                raise


async def get_agent_runtime_config(request: Request) -> AgentRuntimeConfig:
    """Load one immutable config snapshot in a short-lived session.

    This dependency deliberately does not use the request-scoped session: the
    snapshot is read and committed before an SSE response starts, so no database
    connection is held for the lifetime of the stream. Repositories used by the
    run loop remain session-factory backed.
    """
    database = cast(Database, request.app.state.db)
    async with database.session_factory() as session:
        service = AgentSettingsService(AgentConfigRepository(session))
        config = await service.get_runtime_config()
        await session.commit()
    return config


def get_system_prompt_service(request: Request) -> SystemPromptService:
    """Build the singleton prompt service on a short-lived session factory."""
    database = cast(Database, request.app.state.db)
    return SystemPromptService(SystemPromptRepository(database.session_factory))


def get_agent_service(
    request: Request,
    chat_generator: ChatGeneratorProtocol = Depends(get_agent_chat_generator),
    config: AgentRuntimeConfig = Depends(get_agent_runtime_config),
) -> AgentService:
    """Build the agent service with a session-factory-backed repository."""
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    chat_config = runtime.chat_config
    provider = chat_config.provider
    if provider not in {"deepseek", "openai-compatible"}:
        provider = "deepseek"
    model = chat_config.model or "deepseek-flash"
    repository = AgentRepository(request.app.state.db.session_factory)
    tool_registry = AgentToolRegistry(_ToolServiceScope(request))
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
    session: AsyncSession = Depends(get_db_session),
) -> AgentSettingsService:
    """Build settings CRUD on the request transaction; never used for SSE."""
    return AgentSettingsService(AgentConfigRepository(session))


def get_saved_question_service(
    session: AsyncSession = Depends(get_db_session),
) -> SavedQuestionService:
    """Build saved-question CRUD on the request transaction.

    CRUD deliberately does not resolve the chat generator, so questions can be
    captured and edited while the AI provider is not configured.
    """
    return SavedQuestionService(repository=SavedQuestionRepository(session))


def get_saved_question_ask_service(
    session: AsyncSession = Depends(get_db_session),
    agent_service: AgentService = Depends(get_agent_service),
) -> SavedQuestionService:
    """Build the ask orchestrator; a missing provider raises the existing 503.

    ``ask`` is a regular JSON request, so holding the request session while the
    agent runs does not hold a connection for an SSE stream.
    """
    return SavedQuestionService(
        repository=SavedQuestionRepository(session),
        agent_service=agent_service,
    )


__all__ = [
    "ToolServiceScopeProtocol",
    "get_agent_chat_generator",
    "get_agent_runtime_config",
    "get_agent_service",
    "get_agent_settings_service",
    "get_saved_question_ask_service",
    "get_saved_question_service",
]
