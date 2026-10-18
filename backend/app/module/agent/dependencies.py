"""Composition root for the persistent agent slice.

The run loop opens its own short-lived sessions through the application's session
factory. Tool calls use a separate short-lived scope so an SSE response never
holds a request-scoped database session for the lifetime of the stream.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast

from fastapi import Depends, Request

from app.infrastructure.ai.runtime import AiRuntime
from app.module.agent.exception.domain_error import AgentNotConfiguredError
from app.module.agent.protocol.chat_generator_protocol import ChatGeneratorProtocol
from app.module.agent.protocol.tool_service_protocol import (
    AgentToolServices,
    ToolServiceScopeProtocol,
)
from app.module.agent.repository.agent_repository import AgentRepository
from app.module.agent.service.agent_service import AgentService
from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.knowledge.dependencies import (
    get_file_service,
    get_memory_service,
    get_search_service,
    get_timeline_service,
)
from app.module.media.dependencies import (
    get_media_captioner,
    get_media_service,
    get_media_settings,
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
        runtime = cast(AiRuntime, self.request.app.state.ai_runtime)
        settings = get_media_settings(self.request)
        async with self.session_factory() as session:
            try:
                services = AgentToolServices(
                    search_service=get_search_service(self.request, session),
                    file_service=get_file_service(self.request, session),
                    memory_service=get_memory_service(self.request, session),
                    timeline_service=get_timeline_service(self.request, session),
                    media_service=get_media_service(
                        self.request,
                        session,
                        get_media_captioner(self.request, runtime, settings),
                        settings,
                    ),
                )
                yield services
                await session.commit()
            except Exception:
                await session.rollback()
                raise


def get_agent_service(
    request: Request,
    chat_generator: ChatGeneratorProtocol = Depends(get_agent_chat_generator),
) -> AgentService:
    """Build the agent service with a session-factory-backed repository."""
    runtime = cast(AiRuntime, request.app.state.ai_runtime)
    config = runtime.chat_config
    provider = config.provider
    if provider not in {"deepseek", "openai-compatible"}:
        provider = "deepseek"
    model = config.model or "deepseek-flash"
    repository = AgentRepository(request.app.state.db.session_factory)
    tool_registry = AgentToolRegistry(_ToolServiceScope(request))
    return AgentService(
        repository=repository,
        chat_generator=chat_generator,
        tool_registry=tool_registry,
        default_provider=provider,
        default_model=model,
    )


__all__ = ["ToolServiceScopeProtocol", "get_agent_chat_generator", "get_agent_service"]
