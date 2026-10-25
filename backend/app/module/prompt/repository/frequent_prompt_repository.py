"""SQLAlchemy persistence for frequently used prompts.

The repository only knows the request-scoped ``AsyncSession``; the service owns
validation, the 20-row limit, and cache invalidation.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.prompt.model.frequent_prompt_model import FrequentlyUsedPromptModel


class FrequentlyUsedPromptRepository:
    """Request-transaction CRUD for prompt shortcuts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[FrequentlyUsedPromptModel]:
        """Return every prompt in display order.

        ``id`` is the tie-breaker so prompts with the same ``sort_order`` have a
        stable order across reads and cached responses.
        """
        statement = select(FrequentlyUsedPromptModel).order_by(
            FrequentlyUsedPromptModel.sort_order,
            FrequentlyUsedPromptModel.id,
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_all(self) -> int:
        statement = select(func.count()).select_from(FrequentlyUsedPromptModel)
        return int((await self.session.execute(statement)).scalar_one())

    async def add(
        self,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel:
        prompt = FrequentlyUsedPromptModel(
            title=title,
            prompt_text=prompt_text,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def update(
        self,
        prompt_id: int,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel | None:
        prompt = await self.session.get(FrequentlyUsedPromptModel, prompt_id)
        if prompt is None:
            return None
        prompt.title = title
        prompt.prompt_text = prompt_text
        prompt.sort_order = sort_order
        # 明確設定更新時間，避免依賴 ORM 的 onupdate 在批次更新時的行為差異。
        prompt.updated_at = now
        await self.session.flush()
        return prompt

    async def delete(self, prompt_id: int) -> bool:
        prompt = await self.session.get(FrequentlyUsedPromptModel, prompt_id)
        if prompt is None:
            return False
        # 硬刪除：本功能不需要保留歷史，Identity 序號也不會回收。
        await self.session.delete(prompt)
        await self.session.flush()
        return True


__all__ = ["FrequentlyUsedPromptRepository"]
