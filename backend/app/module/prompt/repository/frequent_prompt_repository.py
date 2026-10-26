"""SQLAlchemy persistence for frequently used prompts.

The repository only knows the request-scoped ``AsyncSession``; the service owns
validation, the per-owner 20-row limit, and cache invalidation. Every statement
is scoped to the acting ``user_id`` so row-level security and the repository
filter enforce the same ownership rule.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.prompt.model.frequent_prompt_model import FrequentlyUsedPromptModel


class FrequentlyUsedPromptRepository:
    """Request-transaction CRUD for one owner's prompt shortcuts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: int) -> list[FrequentlyUsedPromptModel]:
        """Return one owner's prompts in display order.

        ``id`` is the tie-breaker so prompts with the same ``sort_order`` have a
        stable order across reads and cached responses.
        """
        statement = (
            select(FrequentlyUsedPromptModel)
            .where(FrequentlyUsedPromptModel.user_id == user_id)
            .order_by(
                FrequentlyUsedPromptModel.sort_order,
                FrequentlyUsedPromptModel.id,
            )
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        """Return how many shortcuts the owner currently has."""
        statement = (
            select(func.count())
            .select_from(FrequentlyUsedPromptModel)
            .where(FrequentlyUsedPromptModel.user_id == user_id)
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def add(
        self,
        *,
        user_id: int,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel:
        prompt = FrequentlyUsedPromptModel(
            user_id=user_id,
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
        user_id: int,
        prompt_id: int,
        *,
        title: str,
        prompt_text: str,
        sort_order: int,
        now: datetime,
    ) -> FrequentlyUsedPromptModel | None:
        """Update one prompt that belongs to ``user_id``.

        A plain primary-key lookup would let another owner's id reach the ORM
        identity map; the explicit owner predicate makes the miss deterministic
        even without row-level security.
        """
        statement = select(FrequentlyUsedPromptModel).where(
            FrequentlyUsedPromptModel.id == prompt_id,
            FrequentlyUsedPromptModel.user_id == user_id,
        )
        prompt = (await self.session.execute(statement)).scalar_one_or_none()
        if prompt is None:
            return None
        prompt.title = title
        prompt.prompt_text = prompt_text
        prompt.sort_order = sort_order
        # Set the timestamp explicitly so batch updates do not depend on
        # SQLAlchemy's ``onupdate`` behavior.
        prompt.updated_at = now
        await self.session.flush()
        return prompt

    async def reorder(
        self,
        user_id: int,
        prompt_ids: list[int],
        *,
        now: datetime,
    ) -> list[FrequentlyUsedPromptModel]:
        """Rewrite ``sort_order`` for one owner's complete collection.

        ``FOR UPDATE`` serializes concurrent reorders, and validation runs after
        the lock: reading ids first would let another request insert or delete a
        row in between, so a payload could pass validation while leaving a row
        out. New orders use ``(index + 1) * 10`` so manual inserts and
        interrupted drags keep integer gaps.
        """
        statement = (
            select(FrequentlyUsedPromptModel)
            .where(FrequentlyUsedPromptModel.user_id == user_id)
            .order_by(
                FrequentlyUsedPromptModel.sort_order,
                FrequentlyUsedPromptModel.id,
            )
            .with_for_update()
        )
        rows = list((await self.session.execute(statement)).scalars().all())
        existing_ids = {row.id for row in rows}
        requested_ids = set(prompt_ids)
        # The payload must cover every prompt owned by the acting user exactly
        # once: no duplicates, no omissions, and no deleted or unknown ids.
        if len(prompt_ids) != len(requested_ids) or requested_ids != existing_ids:
            raise ValueError(
                "The reorder payload must list every existing frequently used prompt exactly once."
            )

        rows_by_id = {row.id: row for row in rows}
        for index, prompt_id in enumerate(prompt_ids):
            row = rows_by_id[prompt_id]
            row.sort_order = (index + 1) * 10
            row.updated_at = now
        await self.session.flush()
        return [rows_by_id[prompt_id] for prompt_id in prompt_ids]

    async def delete(self, user_id: int, prompt_id: int) -> bool:
        """Hard-delete one prompt owned by ``user_id``."""
        statement = select(FrequentlyUsedPromptModel).where(
            FrequentlyUsedPromptModel.id == prompt_id,
            FrequentlyUsedPromptModel.user_id == user_id,
        )
        prompt = (await self.session.execute(statement)).scalar_one_or_none()
        if prompt is None:
            return False
        # Hard delete: this feature keeps no history, and identity ids are never
        # rewound.
        await self.session.delete(prompt)
        await self.session.flush()
        return True


__all__ = ["FrequentlyUsedPromptRepository"]
