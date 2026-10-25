"""Short-lived persistence for the singleton system prompt.

The agent service creates conversations outside a request-scoped transaction and
the SSE loop must never hold a database session. This repository opens one small
session per operation, mirroring the agent transcript repository.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.module.agent.domain.system_prompt_domain import SystemPromptText
from app.module.agent.model.system_prompt_model import SYSTEM_PROMPT_ID, SystemPromptModel


def _record(row: SystemPromptModel) -> SystemPromptText:
    return SystemPromptText(title=row.title, body=row.body, updated_at=row.updated_at)


class SystemPromptRepository:
    """Read, write, and clear the singleton prompt row."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get(self) -> SystemPromptText | None:
        async with self.session_factory() as session:
            row = await session.get(SystemPromptModel, SYSTEM_PROMPT_ID)
            return _record(row) if row is not None else None

    async def save(self, *, title: str, body: str, now: datetime) -> SystemPromptText:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(SystemPromptModel, SYSTEM_PROMPT_ID)
                if row is None:
                    row = SystemPromptModel(id=SYSTEM_PROMPT_ID, title=title, body=body)
                    session.add(row)
                else:
                    row.title = title
                    row.body = body
                    row.updated_at = now
                await session.flush()
                return _record(row)

    async def clear(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(SystemPromptModel, SYSTEM_PROMPT_ID)
                if row is not None:
                    await session.delete(row)
