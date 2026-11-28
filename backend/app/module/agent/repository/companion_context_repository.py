"""Read the companion frozen into one conversation's system entry."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.domain.agent_domain import KIND_SYSTEM
from app.module.agent.domain.companion_persona_domain import frozen_companion
from app.module.agent.model.agent_model import AgentEntryModel


class CompanionContextRepository:
    """Owner-scoped lookup of a conversation's frozen companion."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

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
