"""Consumer-owned persistence contract for frequently used prompts.

Every method takes the acting ``user_id`` explicitly; there is no all-owner
query in the request path.
"""

from datetime import datetime
from typing import Protocol

from app.module.prompt.model.frequent_prompt_model import FrequentlyUsedPromptModel


class FrequentlyUsedPromptRepositoryProtocol(Protocol):
    """CRUD over one owner's prompt shortcuts."""

    async def list_for_user(self, user_id: int) -> list[FrequentlyUsedPromptModel]: ...

    async def count_for_user(self, user_id: int) -> int: ...

    async def add(
        self,
        *,
        user_id: int,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel: ...

    async def update(
        self,
        user_id: int,
        prompt_id: int,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel | None: ...

    async def reorder(
        self,
        user_id: int,
        prompt_ids: list[int],
        *,
        now: datetime,
    ) -> list[FrequentlyUsedPromptModel]: ...

    async def delete(self, user_id: int, prompt_id: int) -> bool: ...


__all__ = ["FrequentlyUsedPromptRepositoryProtocol"]
