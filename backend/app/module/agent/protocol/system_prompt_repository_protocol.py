"""Persistence contract for the singleton custom system prompt."""

from datetime import datetime
from typing import Protocol

from app.module.agent.domain.system_prompt_domain import SystemPromptText


class SystemPromptRepositoryProtocol(Protocol):
    async def get(self) -> SystemPromptText | None: ...

    async def save(self, *, title: str, body: str, now: datetime) -> SystemPromptText: ...

    async def clear(self) -> None: ...
