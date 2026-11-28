"""SQL for account model assignments and the chat endpoint lookup.

Assignments live on ``app_user``, an auth table outside row-level security, so
the root request can read and write them exactly as it does quotas. Endpoint
rows live in ``chat_provider_config``, a global table that is read-all and
root-write. The repository owns the SQL only; validation and probe gating stay in
the service.

``lock_account`` takes ``SELECT ... FOR UPDATE`` on the account row so two
concurrent assignment saves for the same account cannot interleave. The
endpoint rows they reference are loaded and validated in the same transaction.
``write_assignment`` then writes all eight columns in one statement; the caller
owns the transaction.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.auth.model.auth_model import AppUserModel
from app.module.knowledge.model.provider_config_model import ChatProviderConfigModel
from app.shared.time import utcnow


@dataclass(frozen=True)
class AccountAssignment:
    """One account row plus its eight stored assignment columns."""

    user_id: int
    username: str
    updated_at: datetime
    chat_provider_config_id: int | None
    chat_model: str | None
    chat_reasoning_effort: str | None
    aux_provider_config_id: int | None
    aux_model: str | None
    aux_reasoning_effort: str | None
    chat_context_window_tokens: int | None
    chat_compaction_threshold_tokens: int | None


class ModelAssignmentRepository:
    """Read and write the per-account assignment without business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_account_assignments(self) -> list[AccountAssignment]:
        """Return every account and its assignment in one query.

        Root manages membership, so the list includes root itself. No private
        archive row is touched; only the auth table and its assignment columns.
        """
        statement = select(
            AppUserModel.id,
            AppUserModel.username,
            AppUserModel.updated_at,
            AppUserModel.chat_provider_config_id,
            AppUserModel.chat_model,
            AppUserModel.chat_reasoning_effort,
            AppUserModel.aux_provider_config_id,
            AppUserModel.aux_model,
            AppUserModel.aux_reasoning_effort,
            AppUserModel.chat_context_window_tokens,
            AppUserModel.chat_compaction_threshold_tokens,
        ).order_by(AppUserModel.id)
        rows = (await self.session.execute(statement)).all()
        return [
            AccountAssignment(
                user_id=row[0],
                username=row[1],
                updated_at=row[2],
                chat_provider_config_id=row[3],
                chat_model=row[4],
                chat_reasoning_effort=row[5],
                aux_provider_config_id=row[6],
                aux_model=row[7],
                aux_reasoning_effort=row[8],
                chat_context_window_tokens=row[9],
                chat_compaction_threshold_tokens=row[10],
            )
            for row in rows
        ]

    async def get_account(self, user_id: int) -> AppUserModel | None:
        statement = select(AppUserModel).where(AppUserModel.id == user_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def lock_account(self, user_id: int) -> AppUserModel | None:
        """Select one account row ``FOR UPDATE`` before a gated write.

        The lock is held until the request transaction commits or rolls back, so
        two concurrent saves for the same account cannot interleave. The
        referenced endpoint rows are read and validated in the same transaction.
        """
        statement = (
            select(AppUserModel)
            .where(AppUserModel.id == user_id)
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def write_assignment(
        self,
        user_id: int,
        *,
        chat_provider_config_id: int | None,
        chat_model: str | None,
        chat_reasoning_effort: str | None,
        aux_provider_config_id: int | None,
        aux_model: str | None,
        aux_reasoning_effort: str | None,
        chat_context_window_tokens: int | None,
        chat_compaction_threshold_tokens: int | None,
    ) -> None:
        """Write all eight assignment columns in one UPDATE.

        The row is already locked by :meth:`lock_account`. ``updated_at`` is
        stamped here because a Core UPDATE does not run the ORM ``onupdate``.
        """
        await self.session.execute(
            update(AppUserModel)
            .where(AppUserModel.id == user_id)
            .values(
                chat_provider_config_id=chat_provider_config_id,
                chat_model=chat_model,
                chat_reasoning_effort=chat_reasoning_effort,
                aux_provider_config_id=aux_provider_config_id,
                aux_model=aux_model,
                aux_reasoning_effort=aux_reasoning_effort,
                chat_context_window_tokens=chat_context_window_tokens,
                chat_compaction_threshold_tokens=chat_compaction_threshold_tokens,
                updated_at=utcnow(),
            )
        )

    async def get_chat_rows(
        self,
        row_ids: Iterable[int],
    ) -> dict[int, ChatProviderConfigModel]:
        """Load the referenced endpoint rows for validation and labels."""
        unique_ids = sorted({row_id for row_id in row_ids})
        if not unique_ids:
            return {}
        statement = select(ChatProviderConfigModel).where(
            ChatProviderConfigModel.id.in_(unique_ids)
        )
        rows = (await self.session.execute(statement)).scalars().all()
        return {row.id: row for row in rows}

    async def list_chat_rows(self) -> list[ChatProviderConfigModel]:
        """Return every saved chat endpoint, active rows first."""
        statement = select(ChatProviderConfigModel).order_by(
            ChatProviderConfigModel.is_active.desc(),
            ChatProviderConfigModel.priority,
            ChatProviderConfigModel.id,
        )
        return list((await self.session.execute(statement)).scalars().all())


__all__ = ["AccountAssignment", "ModelAssignmentRepository"]
