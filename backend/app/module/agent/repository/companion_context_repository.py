"""Read the companion frozen into one conversation's system entry."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.domain.agent_domain import KIND_SYSTEM, KIND_USER
from app.module.agent.domain.companion_persona_domain import (
    COMPANION_SWITCH_KEY,
    GUIDANCE_VERSION_KEY,
    current_companion,
)
from app.module.agent.model.agent_model import AgentEntryModel


class CompanionContextRepository:
    """Owner-scoped lookup of a conversation's current companion.

    The current companion is the one named by the latest handoff on a user entry,
    or the one frozen in the system entry when the conversation was never handed off.
    """

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def conversation_identity(
        self,
        conversation_id: int,
    ) -> tuple[str, str, str] | None:
        """Return ``(ref, name, locale)`` of the current companion, or ``None``."""
        current = await self.current(conversation_id)
        if current is None:
            return None
        return current["ref"], current["name"], current["locale"]

    async def current(self, conversation_id: int) -> dict[str, str] | None:
        """Return ``{ref, name, locale}`` of whoever speaks now, or ``None``."""
        return current_companion(
            await self._system_data(conversation_id),
            await self._latest_switch_data(conversation_id),
        )

    async def guidance_version(self, conversation_id: int) -> str | None:
        """Return the prompt version the conversation's guidance was last given at."""
        statement = (
            select(AgentEntryModel.data[GUIDANCE_VERSION_KEY].astext)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.kind == KIND_USER,
                AgentEntryModel.data.has_key(GUIDANCE_VERSION_KEY),
            )
            .order_by(AgentEntryModel.id.desc())
            .limit(1)
        )
        stamped = (await self.session.execute(statement)).scalar_one_or_none()
        if stamped:
            return str(stamped)
        system = await self._system_data(conversation_id)
        if isinstance(system, dict):
            version = system.get("prompt_version")
            if isinstance(version, str):
                return version
        return None

    async def _latest_switch_data(self, conversation_id: int) -> Any:
        statement = (
            select(AgentEntryModel.data)
            .where(
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.kind == KIND_USER,
                AgentEntryModel.data.has_key(COMPANION_SWITCH_KEY),
            )
            .order_by(AgentEntryModel.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

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
        """Return ``(ref, locale)`` of the current companion, or ``None``."""
        current = await self.current(conversation_id)
        if current is None:
            return None
        return current["ref"], current["locale"]


__all__ = ["CompanionContextRepository"]
