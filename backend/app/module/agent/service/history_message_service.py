"""Read one past conversation message and its immediate neighbours."""

from app.infrastructure.database.session import Database
from app.module.agent.domain.agent_domain import KIND_USER
from app.module.agent.domain.history_domain import (
    HISTORY_MESSAGE_NEIGHBOR_LIMIT,
    HistoryMessage,
    HistoryMessageRead,
    entry_message_text,
)
from app.module.agent.exception.domain_error import AgentHistoryMessageNotFoundError
from app.module.agent.model.agent_model import AgentConversationModel, AgentEntryModel
from app.module.agent.repository.history_repository import AgentHistoryRepository


def _message(entry: AgentEntryModel, conversation: AgentConversationModel) -> HistoryMessage:
    return HistoryMessage(
        entry_id=entry.id,
        conversation_id=conversation.id,
        conversation_title=conversation.title,
        role="user" if entry.kind == KIND_USER else "assistant",
        created_at=entry.created_at,
        content=entry_message_text(entry.kind, entry.model),
    )


class AgentHistoryMessageService:
    """Owner-bound reads for the ``history_message`` agent tool.

    The service opens one short owner-scoped session per call; it never reads
    another account's transcript and never returns a soft-deleted conversation.
    """

    def __init__(
        self,
        *,
        database: Database,
        user_id: int,
        role: str,
    ) -> None:
        self.database = database
        self.user_id = user_id
        self.role = role

    async def read_message(
        self,
        message_id: int,
        *,
        message_range: int = 1,
    ) -> HistoryMessageRead:
        """Read one message and at most ``message_range`` neighbours on each side."""
        bounded_range = max(0, min(int(message_range), HISTORY_MESSAGE_NEIGHBOR_LIMIT))
        async with self.database.user_session(self.user_id, self.role) as session:
            repository = AgentHistoryRepository(session, user_id=self.user_id)
            row = await repository.get_message(message_id)
            if row is None:
                raise AgentHistoryMessageNotFoundError(message_id)
            entry, conversation = row
            before_rows, after_rows = await repository.get_neighbors(
                conversation_id=conversation.id,
                entry_id=entry.id,
                before=bounded_range,
                after=bounded_range,
            )
            return HistoryMessageRead(
                target=_message(entry, conversation),
                before=[
                    message
                    for message in (_message(item, conversation) for item in before_rows)
                    if message.content
                ],
                after=[
                    message
                    for message in (_message(item, conversation) for item in after_rows)
                    if message.content
                ],
            )


__all__ = ["AgentHistoryMessageService"]
