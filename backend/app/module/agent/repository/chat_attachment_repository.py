"""Owner-scoped persistence for temporary chat images."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.agent.model.agent_model import AgentChatAttachmentModel


class ChatAttachmentRepository:
    """One account's temporary images, one short transaction per operation."""

    def __init__(self, database: Database, *, user_id: int, role: str) -> None:
        self.database = database
        self.user_id = user_id
        self.role = role

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.database.user_session(self.user_id, self.role) as session:
            yield session

    @asynccontextmanager
    async def _read(self) -> AsyncIterator[AsyncSession]:
        async with self.database.user_session(self.user_id, self.role) as session:
            yield session

    async def add(
        self,
        *,
        storage_key: str,
        storage_backend: str,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        width: int,
        height: int,
        content_hash: str,
        created_at: datetime,
        client_token: str | None = None,
    ) -> AgentChatAttachmentModel:
        """Insert one staged image."""
        async with self._transaction() as session:
            row = AgentChatAttachmentModel(
                user_id=self.user_id,
                client_token=client_token,
                storage_key=storage_key,
                storage_backend=storage_backend,
                file_name=file_name,
                mime_type=mime_type,
                size_bytes=size_bytes,
                width=width,
                height=height,
                content_hash=content_hash,
                created_at=created_at,
            )
            session.add(row)
            await session.flush()
            return row

    async def get(self, attachment_id: int) -> AgentChatAttachmentModel | None:
        """Return one live-owned row, including attached images."""
        async with self._read() as session:
            statement = select(AgentChatAttachmentModel).where(
                AgentChatAttachmentModel.id == attachment_id,
                AgentChatAttachmentModel.user_id == self.user_id,
                AgentChatAttachmentModel.deleted_at.is_(None),
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def get_by_client_token(
        self,
        client_token: str,
    ) -> AgentChatAttachmentModel | None:
        """Return the live row a browser token already produced, if any."""
        async with self._read() as session:
            statement = select(AgentChatAttachmentModel).where(
                AgentChatAttachmentModel.user_id == self.user_id,
                AgentChatAttachmentModel.client_token == client_token,
                AgentChatAttachmentModel.deleted_at.is_(None),
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def page(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentChatAttachmentModel], int]:
        """Page through the account's temporary images, newest first."""
        async with self._read() as session:
            statement = select(AgentChatAttachmentModel).where(
                AgentChatAttachmentModel.user_id == self.user_id,
                AgentChatAttachmentModel.deleted_at.is_(None),
            )
            count_statement = select(func.count()).select_from(
                AgentChatAttachmentModel
            ).where(
                AgentChatAttachmentModel.user_id == self.user_id,
                AgentChatAttachmentModel.deleted_at.is_(None),
            )
            if status == "staged":
                statement = statement.where(AgentChatAttachmentModel.entry_id.is_(None))
                count_statement = count_statement.where(
                    AgentChatAttachmentModel.entry_id.is_(None)
                )
            elif status == "attached":
                statement = statement.where(AgentChatAttachmentModel.entry_id.is_not(None))
                count_statement = count_statement.where(
                    AgentChatAttachmentModel.entry_id.is_not(None)
                )
            rows = list(
                (
                    await session.execute(
                        statement.order_by(
                            AgentChatAttachmentModel.created_at.desc(),
                            AgentChatAttachmentModel.id.desc(),
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            total = int((await session.execute(count_statement)).scalar_one())
            return rows, total

    async def mark_deleted(self, attachment_id: int, *, now: datetime) -> bool:
        """Soft-delete one row; repeated calls report no change."""
        async with self._transaction() as session:
            result = await session.execute(
                update(AgentChatAttachmentModel)
                .where(
                    AgentChatAttachmentModel.id == attachment_id,
                    AgentChatAttachmentModel.user_id == self.user_id,
                    AgentChatAttachmentModel.deleted_at.is_(None),
                )
                .values(deleted_at=now)
            )
            return int(getattr(result, "rowcount", 0) or 0) > 0

    async def claim_staged_by_token(
        self,
        client_token: str,
        *,
        now: datetime,
    ) -> tuple[str, str] | None:
        """Soft-delete one staged upload and return its object reference.

        The conditional update is the race guard against a message claiming the
        same image. An attached image never matches, so cancelling an upload is
        a no-op once the message owns it. The caller removes the returned object
        only after this transaction commits.
        """
        async with self._transaction() as session:
            result = await session.execute(
                update(AgentChatAttachmentModel)
                .where(
                    AgentChatAttachmentModel.user_id == self.user_id,
                    AgentChatAttachmentModel.client_token == client_token,
                    AgentChatAttachmentModel.deleted_at.is_(None),
                    AgentChatAttachmentModel.entry_id.is_(None),
                )
                .values(deleted_at=now)
                .returning(
                    AgentChatAttachmentModel.storage_key,
                    AgentChatAttachmentModel.storage_backend,
                )
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return str(row["storage_key"]), str(row["storage_backend"])

    async def update_storage(
        self,
        attachment_id: int,
        *,
        storage_key: str,
        storage_backend: str,
    ) -> bool:
        """Point one live row at its promoted durable object."""
        async with self._transaction() as session:
            result = await session.execute(
                update(AgentChatAttachmentModel)
                .where(
                    AgentChatAttachmentModel.id == attachment_id,
                    AgentChatAttachmentModel.user_id == self.user_id,
                    AgentChatAttachmentModel.deleted_at.is_(None),
                )
                .values(
                    storage_key=storage_key,
                    storage_backend=storage_backend,
                )
            )
            return int(getattr(result, "rowcount", 0) or 0) > 0

    async def list_by_ids(
        self,
        attachment_ids: Sequence[int],
    ) -> list[AgentChatAttachmentModel]:
        """Return live images referenced by the supplied entry data ids."""
        if not attachment_ids:
            return []
        async with self._read() as session:
            statement = (
                select(AgentChatAttachmentModel)
                .where(
                    AgentChatAttachmentModel.user_id == self.user_id,
                    AgentChatAttachmentModel.id.in_(attachment_ids),
                    AgentChatAttachmentModel.deleted_at.is_(None),
                )
                .order_by(AgentChatAttachmentModel.id.asc())
            )
            return list((await session.execute(statement)).scalars().all())


__all__ = ["ChatAttachmentRepository"]
