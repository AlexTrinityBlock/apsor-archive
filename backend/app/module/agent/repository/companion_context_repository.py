"""Read the companion frozen into one conversation's system entry."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.domain.agent_domain import KIND_SYSTEM
from app.module.agent.domain.companion_persona_domain import (
    frozen_companion,
    frozen_speaker,
)
from app.module.agent.model.agent_model import AgentEntryModel


class CompanionContextRepository:
    """Owner-scoped lookup of a conversation's frozen companion."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def conversation_identity(
        self,
        conversation_id: int,
    ) -> tuple[str, str, str] | None:
        """Return ``(ref, name, locale)`` of the frozen companion, or ``None``."""
        data = await self._system_data(conversation_id)
        frozen = frozen_companion(data)
        speaker = frozen_speaker(data)
        if frozen is None or speaker is None:
            return None
        return frozen[0], speaker["name"], frozen[1]

    async def _system_data(self, conversation_id: int) -> Any:
        statement = (
            select(AgentEntryModel.data)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.kind == KIND_SYSTEM,
            )
            .order_by(AgentEntryModel.id)
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def conversation_companion(self, conversation_id: int) -> tuple[str, str] | None:
        """Return ``(ref, locale)`` frozen at creation, or ``None``."""
        statement = (
            select(AgentEntryModel.data)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.kind == KIND_SYSTEM,
            )
            .order_by(AgentEntryModel.id)
            .limit(1)
        )
        data: Any = (await self.session.execute(statement)).scalar_one_or_none()
        return frozen_companion(data)


__all__ = ["CompanionContextRepository"]
