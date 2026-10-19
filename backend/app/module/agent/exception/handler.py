"""Register agent-domain errors with the global exception registry."""

from app.module.agent.exception.domain_error import (
    AgentConversationArchivedError,
    AgentConversationBusyError,
    AgentConversationNotFoundError,
    AgentError,
    AgentInvalidEntryError,
    AgentNotConfiguredError,
    AgentProviderError,
    AgentRequestDuplicateError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
    AgentRunNotRetryableError,
    SavedQuestionNotFoundError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    """Map each agent error to an HTTP status and a stable error code."""
    ExceptionRegistry.register(AgentConversationNotFoundError, 404, "agent_conversation_not_found")
    ExceptionRegistry.register(AgentConversationArchivedError, 409, "agent_conversation_archived")
    ExceptionRegistry.register(AgentConversationBusyError, 409, "agent_conversation_busy")
    ExceptionRegistry.register(AgentRequestDuplicateError, 409, "agent_request_duplicate")
    ExceptionRegistry.register(AgentRunNotFoundError, 404, "agent_run_not_found")
    ExceptionRegistry.register(AgentRunNotRetryableError, 409, "agent_run_not_retryable")
    ExceptionRegistry.register(AgentRunNotActiveError, 409, "agent_run_not_active")
    ExceptionRegistry.register(AgentNotConfiguredError, 503, "agent_not_configured")
    ExceptionRegistry.register(AgentProviderError, 502, "agent_provider_error")
    ExceptionRegistry.register(AgentInvalidEntryError, 422, "agent_invalid_entry")
    ExceptionRegistry.register(SavedQuestionNotFoundError, 404, "saved_question_not_found")
    ExceptionRegistry.register(AgentError, 500, "agent_error")
