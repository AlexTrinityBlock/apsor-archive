"""Consumer-owned persistence contract for frequently used prompts."""

from datetime import datetime
from typing import Protocol

from app.module.prompt.model.frequent_prompt_model import FrequentlyUsedPromptModel


class FrequentlyUsedPromptRepositoryProtocol(Protocol):
    """CRUD over the owner-editable prompt shortcuts."""

    async def list_all(self) -> list[FrequentlyUsedPromptModel]: ...

    async def count_all(self) -> int: ...

    async def add(
        self,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel: ...

    async def update(
        self,
        prompt_id: int,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel | None: ...

    async def delete(self, prompt_id: int) -> bool: ...


__all__ = ["FrequentlyUsedPromptRepositoryProtocol"]
