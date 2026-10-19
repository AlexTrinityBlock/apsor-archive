"""Domain errors for the persistent agent slice."""


class AgentError(Exception):
    """Base class for every agent-domain failure."""


class AgentConversationNotFoundError(AgentError):
    def __init__(self, conversation_id: int) -> None:
        super().__init__(f"Agent conversation {conversation_id} was not found.")


class AgentConversationArchivedError(AgentError):
    def __init__(self, conversation_id: int) -> None:
        super().__init__(f"Agent conversation {conversation_id} is archived.")


class AgentConversationBusyError(AgentError):
    def __init__(self, conversation_id: int) -> None:
        super().__init__(f"Agent conversation {conversation_id} already has an active run.")


class AgentRequestDuplicateError(AgentError):
    def __init__(self, request_id: str) -> None:
        super().__init__(f"Request id {request_id} was already used in this conversation.")


class AgentRunNotFoundError(AgentError):
    def __init__(self, run_id: int | None = None) -> None:
        detail = (
            "No agent run was found."
            if run_id is None
            else f"Agent run {run_id} was not found."
        )
        super().__init__(detail)


class AgentRunNotRetryableError(AgentError):
    def __init__(self, status: str) -> None:
        super().__init__(f"The latest agent run is {status} and cannot be retried.")


class AgentRunNotActiveError(AgentError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"Agent run {run_id} is no longer active.")


class AgentNotConfiguredError(AgentError):
    def __init__(self) -> None:
        super().__init__("No chat provider is configured for agent conversations.")


class AgentProviderError(AgentError):
    def __init__(self) -> None:
        super().__init__("The chat provider failed.")


class AgentInvalidEntryError(AgentError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class SavedQuestionNotFoundError(AgentError):
    def __init__(self, question_id: int) -> None:
        super().__init__(f"Saved question {question_id} was not found.")
