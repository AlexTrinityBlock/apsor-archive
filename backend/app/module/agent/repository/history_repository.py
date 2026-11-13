"""Owner-scoped reads over immutable conversation entries.

The history indexer and the ``history_message`` tool both need the same narrow
view of a transcript: a user or assistant message, its conversation metadata,
and a few adjacent messages. Entries and conversations stay in the agent slice;
only the search windows live in the shared knowledge chunk table.
"""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.domain.history_domain import HISTORY_INDEXED_KINDS
from app.module.agent.model.agent_model import AgentConversationModel, AgentEntryModel


class AgentHistoryRepository:
    """One owner's transcript reads inside one caller-owned session."""

    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def get_entries(self, entry_ids: list[int]) -> list[AgentEntryModel]:
        """Load immutable entries by id in ascending order."""
        if not entry_ids:
            return []
        statement = (
            select(AgentEntryModel)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.id.in_(entry_ids),
                AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
            )
            .order_by(AgentEntryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_entries_with_conversations(
        self,
        entry_ids: list[int],
    ) -> list[tuple[AgentEntryModel, AgentConversationModel]]:
        """Load entries together with their non-deleted conversation."""
        if not entry_ids:
            return []
        statement = (
            select(AgentEntryModel, AgentConversationModel)
            .join(
                AgentConversationModel,
                and_(
                    AgentConversationModel.id == AgentEntryModel.conversation_id,
                    AgentConversationModel.user_id == AgentEntryModel.user_id,
                ),
            )
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.id.in_(entry_ids),
                AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
                AgentConversationModel.deleted_at.is_(None),
            )
            .order_by(AgentEntryModel.id)
        )
        return [
            (entry, conversation)
            for entry, conversation in (await self.session.execute(statement)).all()
        ]

    async def get_message(
        self,
        entry_id: int,
    ) -> tuple[AgentEntryModel, AgentConversationModel] | None:
        """Load one live user/assistant message and its conversation."""
        statement = (
            select(AgentEntryModel, AgentConversationModel)
            .join(
                AgentConversationModel,
                and_(
                    AgentConversationModel.id == AgentEntryModel.conversation_id,
                    AgentConversationModel.user_id == AgentEntryModel.user_id,
                ),
            )
            .where(
                AgentEntryModel.id == entry_id,
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
                AgentConversationModel.deleted_at.is_(None),
            )
        )
        row = (await self.session.execute(statement)).first()
        return None if row is None else (row[0], row[1])

    async def get_neighbors(
        self,
        *,
        conversation_id: int,
        entry_id: int,
        before: int,
        after: int,
    ) -> tuple[list[AgentEntryModel], list[AgentEntryModel]]:
        """Return adjacent user/assistant messages in chronological order."""
        before_rows: list[AgentEntryModel] = []
        if before > 0:
            statement = (
                select(AgentEntryModel)
                .where(
                    AgentEntryModel.user_id == self.user_id,
                    AgentEntryModel.conversation_id == conversation_id,
                    AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
                    AgentEntryModel.id < entry_id,
                )
                .order_by(AgentEntryModel.id.desc())
                .limit(before)
            )
            before_rows = list((await self.session.execute(statement)).scalars().all())
            before_rows.reverse()

        after_rows: list[AgentEntryModel] = []
        if after > 0:
            statement = (
                select(AgentEntryModel)
                .where(
                    AgentEntryModel.user_id == self.user_id,
                    AgentEntryModel.conversation_id == conversation_id,
                    AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
                    AgentEntryModel.id > entry_id,
                )
                .order_by(AgentEntryModel.id.asc())
                .limit(after)
            )
            after_rows = list((await self.session.execute(statement)).scalars().all())
        return before_rows, after_rows

    async def conversation_entry_ids(self, conversation_id: int) -> list[int]:
        """Return every indexable entry id in one conversation.

        The conversation may already be soft-deleted; this is used to retire
        its search windows.
        """
        statement = (
            select(AgentEntryModel.id)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.kind.in_(HISTORY_INDEXED_KINDS),
            )
            .order_by(AgentEntryModel.id)
        )
        return [int(entry_id) for entry_id in (await self.session.execute(statement)).scalars()]


__all__ = ["AgentHistoryRepository"]
