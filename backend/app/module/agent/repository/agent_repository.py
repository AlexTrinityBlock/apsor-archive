"""SQLAlchemy persistence for the append-only agent transcript.

Every write opens its own short session and transaction. This is deliberate: the
SSE turn loop must not hold a request-scoped session for the lifetime of the
stream. Each append transaction reserves one ``agent_commit_seq`` value and uses
it for every entry written in that transaction.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.module.agent.domain.agent_domain import (
    ACTIVE_RUN_STATUSES,
    CONVERSATION_ACTIVE,
    CONVERSATION_ARCHIVED,
    KIND_SYSTEM,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_RUNNING,
    TERMINAL_RUN_STATUSES,
    EntryDraft,
)
from app.module.agent.exception.domain_error import (
    AgentConversationArchivedError,
    AgentConversationBusyError,
    AgentConversationNotFoundError,
    AgentRequestDuplicateError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
)
from app.module.agent.model.agent_model import (
    AGENT_COMMIT_SEQUENCE,
    AgentConversationModel,
    AgentEntryModel,
    AgentRunModel,
)


class AgentRepository:
    """Repository with one transaction per public mutation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            async with session.begin():
                yield session

    @asynccontextmanager
    async def _read(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    @staticmethod
    async def _next_commit_seq(session: AsyncSession) -> int:
        value = await session.execute(
            text("SELECT nextval(:name)"),
            {"name": AGENT_COMMIT_SEQUENCE.name},
        )
        return int(value.scalar_one())

    @staticmethod
    async def _lock_conversation(
        session: AsyncSession,
        conversation_id: int,
    ) -> AgentConversationModel:
        statement = (
            select(AgentConversationModel)
            .where(AgentConversationModel.id == conversation_id)
            .with_for_update()
        )
        conversation = (await session.execute(statement)).scalar_one_or_none()
        if conversation is None or conversation.deleted_at is not None:
            raise AgentConversationNotFoundError(conversation_id)
        return conversation

    @staticmethod
    async def _lock_active_run(
        session: AsyncSession,
        conversation_id: int,
        run_id: int,
    ) -> AgentRunModel:
        statement = (
            select(AgentRunModel)
            .where(
                AgentRunModel.id == run_id,
                AgentRunModel.conversation_id == conversation_id,
            )
            .with_for_update()
        )
        run = (await session.execute(statement)).scalar_one_or_none()
        if run is None:
            raise AgentRunNotFoundError(run_id)
        if run.status not in ACTIVE_RUN_STATUSES or run.abort_requested:
            raise AgentRunNotActiveError(run_id)
        return run

    async def create_conversation(
        self,
        *,
        title: str,
        provider: str,
        model: str,
        provider_session_id: UUID,
        system_model: list[dict[str, Any]],
        system_data: dict[str, Any],
        now: datetime,
    ) -> tuple[AgentConversationModel, AgentEntryModel]:
        async with self._transaction() as session:
            conversation = AgentConversationModel(
                title=title,
                provider=provider,
                model=model,
                provider_session_id=provider_session_id,
                status=CONVERSATION_ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(conversation)
            await session.flush()

            commit_seq = await self._next_commit_seq(session)
            entry = AgentEntryModel(
                conversation_id=conversation.id,
                commit_seq=commit_seq,
                kind=KIND_SYSTEM,
                model=system_model,
                data=system_data,
                created_at=now,
            )
            session.add(entry)
            await session.flush()
            conversation.last_entry_at = entry.created_at
            return conversation, entry

    async def get_conversation(
        self,
        conversation_id: int,
        *,
        include_deleted: bool = False,
    ) -> AgentConversationModel | None:
        async with self._read() as session:
            conversation = await session.get(AgentConversationModel, conversation_id)
            if conversation is None:
                return None
            if not include_deleted and conversation.deleted_at is not None:
                return None
            return conversation

    async def list_conversations(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[AgentConversationModel]:
        async with self._read() as session:
            statement = select(AgentConversationModel).where(
                AgentConversationModel.deleted_at.is_(None)
            )
            if status is not None:
                statement = statement.where(AgentConversationModel.status == status)
            statement = (
                statement.order_by(
                    AgentConversationModel.last_entry_at.desc().nulls_last(),
                    AgentConversationModel.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return list((await session.execute(statement)).scalars().all())

    async def count_conversations(self, *, status: str | None) -> int:
        async with self._read() as session:
            statement = select(func.count()).select_from(AgentConversationModel).where(
                AgentConversationModel.deleted_at.is_(None)
            )
            if status is not None:
                statement = statement.where(AgentConversationModel.status == status)
            return int((await session.execute(statement)).scalar_one())

    async def update_conversation(
        self,
        conversation_id: int,
        *,
        title: str | None,
        status: str | None,
        now: datetime,
    ) -> AgentConversationModel | None:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(session, conversation_id)
            if title is not None:
                conversation.title = title
            if status is not None:
                if status == CONVERSATION_ARCHIVED and conversation.status != CONVERSATION_ARCHIVED:
                    conversation.archived_at = now
                if status == CONVERSATION_ACTIVE:
                    conversation.archived_at = None
                conversation.status = status
            conversation.updated_at = now
            return conversation

    async def soft_delete_conversation(
        self,
        conversation_id: int,
        *,
        now: datetime,
    ) -> bool:
        async with self._transaction() as session:
            statement = (
                select(AgentConversationModel)
                .where(AgentConversationModel.id == conversation_id)
                .with_for_update()
            )
            conversation = (await session.execute(statement)).scalar_one_or_none()
            if conversation is None or conversation.deleted_at is not None:
                return False
            conversation.deleted_at = now
            conversation.archived_at = conversation.archived_at or now
            conversation.status = CONVERSATION_ARCHIVED
            conversation.updated_at = now
            await session.execute(
                update(AgentRunModel)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                )
                .values(
                    status=RUN_CANCELLED,
                    abort_requested=True,
                    error_code="aborted",
                    error_detail="The conversation was deleted.",
                    finished_at=now,
                )
            )
            return True

    async def append_user_and_run(
        self,
        *,
        conversation_id: int,
        draft: EntryDraft,
        request_id: str | None,
        now: datetime,
    ) -> tuple[AgentConversationModel, AgentEntryModel, AgentRunModel]:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(session, conversation_id)
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation_id)

            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                )
                .limit(1)
            )
            if active.scalar_one_or_none() is not None:
                raise AgentConversationBusyError(conversation_id)

            if request_id is not None:
                duplicate = await session.execute(
                    select(AgentRunModel.id)
                    .where(
                        AgentRunModel.conversation_id == conversation_id,
                        AgentRunModel.request_id == request_id,
                    )
                    .limit(1)
                )
                if duplicate.scalar_one_or_none() is not None:
                    raise AgentRequestDuplicateError(request_id)

            commit_seq = await self._next_commit_seq(session)
            entry = AgentEntryModel(
                conversation_id=conversation_id,
                commit_seq=commit_seq,
                kind=draft.kind,
                model=draft.messages,
                data=draft.data,
                created_at=now,
            )
            session.add(entry)
            await session.flush()

            run = AgentRunModel(
                conversation_id=conversation_id,
                request_id=request_id,
                user_entry_id=entry.id,
                status=RUN_RUNNING,
                last_entry_id=entry.id,
                started_at=now,
                created_at=now,
            )
            session.add(run)
            await session.flush()
            entry.by_run_id = run.id
            conversation.last_entry_at = entry.created_at
            await session.flush()
            return conversation, entry, run

    async def create_run(
        self,
        *,
        conversation_id: int,
        user_entry_id: int,
        last_entry_id: int,
        request_id: str | None,
        now: datetime,
    ) -> AgentRunModel:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(session, conversation_id)
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation_id)
            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                )
                .limit(1)
            )
            if active.scalar_one_or_none() is not None:
                raise AgentConversationBusyError(conversation_id)
            if request_id is not None:
                duplicate = await session.execute(
                    select(AgentRunModel.id)
                    .where(
                        AgentRunModel.conversation_id == conversation_id,
                        AgentRunModel.request_id == request_id,
                    )
                    .limit(1)
                )
                if duplicate.scalar_one_or_none() is not None:
                    raise AgentRequestDuplicateError(request_id)
            run = AgentRunModel(
                conversation_id=conversation_id,
                request_id=request_id,
                user_entry_id=user_entry_id,
                status=RUN_RUNNING,
                last_entry_id=last_entry_id,
                started_at=now,
                created_at=now,
            )
            session.add(run)
            await session.flush()
            return run

    async def append_assistant(
        self,
        *,
        conversation_id: int,
        run_id: int,
        draft: EntryDraft,
        now: datetime,
    ) -> AgentEntryModel:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(session, conversation_id)
            run = await self._lock_active_run(session, conversation_id, run_id)
            commit_seq = await self._next_commit_seq(session)
            entry = AgentEntryModel(
                conversation_id=conversation_id,
                commit_seq=commit_seq,
                kind=draft.kind,
                model=draft.messages,
                data=draft.data,
                by_run_id=run.id,
                created_at=now,
            )
            session.add(entry)
            await session.flush()
            run.last_entry_id = entry.id
            conversation.last_entry_at = entry.created_at
            return entry

    async def append_tool_results(
        self,
        *,
        conversation_id: int,
        run_id: int,
        drafts: list[EntryDraft],
        now: datetime,
    ) -> list[AgentEntryModel]:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(session, conversation_id)
            run = await self._lock_active_run(session, conversation_id, run_id)
            commit_seq = await self._next_commit_seq(session)
            entries: list[AgentEntryModel] = []
            for draft in drafts:
                entry = AgentEntryModel(
                    conversation_id=conversation_id,
                    commit_seq=commit_seq,
                    kind=draft.kind,
                    model=draft.messages,
                    data=draft.data,
                    by_run_id=run.id,
                    created_at=now,
                )
                session.add(entry)
                entries.append(entry)
            await session.flush()
            if entries:
                run.last_entry_id = entries[-1].id
                conversation.last_entry_at = entries[-1].created_at
            return entries

    async def complete_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        last_entry_id: int | None,
        now: datetime,
    ) -> None:
        await self._settle_run(
            conversation_id=conversation_id,
            run_id=run_id,
            status=RUN_COMPLETED,
            error_code=None,
            error_detail=None,
            last_entry_id=last_entry_id,
            now=now,
        )

    async def fail_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        error_code: str,
        error_detail: str,
        last_entry_id: int | None,
        now: datetime,
    ) -> None:
        await self._settle_run(
            conversation_id=conversation_id,
            run_id=run_id,
            status=RUN_FAILED,
            error_code=error_code,
            error_detail=error_detail[:1000],
            last_entry_id=last_entry_id,
            now=now,
        )

    async def cancel_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        last_entry_id: int | None,
        now: datetime,
    ) -> None:
        await self._settle_run(
            conversation_id=conversation_id,
            run_id=run_id,
            status=RUN_CANCELLED,
            error_code="aborted",
            error_detail="The client disconnected or stopped the run.",
            last_entry_id=last_entry_id,
            now=now,
        )

    async def _settle_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        status: str,
        error_code: str | None,
        error_detail: str | None,
        last_entry_id: int | None,
        now: datetime,
    ) -> None:
        async with self._transaction() as session:
            statement = (
                select(AgentRunModel)
                .where(
                    AgentRunModel.id == run_id,
                    AgentRunModel.conversation_id == conversation_id,
                )
                .with_for_update()
            )
            run = (await session.execute(statement)).scalar_one_or_none()
            if run is None:
                raise AgentRunNotFoundError(run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return
            run.status = status
            run.abort_requested = status == RUN_CANCELLED
            run.error_code = error_code
            run.error_detail = error_detail
            run.finished_at = now
            if last_entry_id is not None:
                run.last_entry_id = last_entry_id

    async def get_run(self, run_id: int) -> AgentRunModel | None:
        async with self._read() as session:
            return await session.get(AgentRunModel, run_id)

    async def get_latest_run(self, conversation_id: int) -> AgentRunModel | None:
        async with self._read() as session:
            statement = (
                select(AgentRunModel)
                .where(AgentRunModel.conversation_id == conversation_id)
                .order_by(AgentRunModel.id.desc())
                .limit(1)
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def get_entry(self, entry_id: int) -> AgentEntryModel | None:
        async with self._read() as session:
            return await session.get(AgentEntryModel, entry_id)

    async def latest_entry_id(self, conversation_id: int) -> int | None:
        async with self._read() as session:
            statement = select(func.max(AgentEntryModel.id)).where(
                AgentEntryModel.conversation_id == conversation_id
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def list_run_entries(self, run_id: int) -> list[AgentEntryModel]:
        async with self._read() as session:
            statement = (
                select(AgentEntryModel)
                .where(AgentEntryModel.by_run_id == run_id)
                .order_by(AgentEntryModel.id.asc())
            )
            return list((await session.execute(statement)).scalars().all())

    async def load_context_entries(
        self,
        conversation_id: int,
        *,
        cutoff_entry_id: int | None,
    ) -> list[AgentEntryModel]:
        async with self._read() as session:
            statement = select(AgentEntryModel).where(
                AgentEntryModel.conversation_id == conversation_id
            )
            if cutoff_entry_id is not None:
                statement = statement.where(AgentEntryModel.id <= cutoff_entry_id)
            statement = statement.order_by(AgentEntryModel.id.asc())
            return list((await session.execute(statement)).scalars().all())

    async def list_entries(
        self,
        conversation_id: int,
        *,
        after_id: int | None,
        limit: int,
    ) -> tuple[list[AgentEntryModel], bool]:
        async with self._read() as session:
            statement = select(AgentEntryModel).where(
                AgentEntryModel.conversation_id == conversation_id
            )
            if after_id is not None:
                statement = statement.where(AgentEntryModel.id > after_id)
            statement = (
                statement.order_by(AgentEntryModel.id.asc()).limit(limit + 1)
            )
            rows = list((await session.execute(statement)).scalars().all())
            has_more = len(rows) > limit
            return rows[:limit], has_more

    async def count_entries(self, conversation_id: int) -> int:
        async with self._read() as session:
            statement = select(func.count()).select_from(AgentEntryModel).where(
                AgentEntryModel.conversation_id == conversation_id
            )
            return int((await session.execute(statement)).scalar_one())

    async def is_abort_requested(self, conversation_id: int, run_id: int) -> bool:
        async with self._read() as session:
            statement = select(AgentRunModel.status, AgentRunModel.abort_requested).where(
                AgentRunModel.id == run_id,
                AgentRunModel.conversation_id == conversation_id,
            )
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return True
            status, abort_requested = row
            return bool(abort_requested) or status in TERMINAL_RUN_STATUSES

    async def mark_interrupted_runs(self, *, now: datetime) -> int:
        async with self._transaction() as session:
            result = await session.execute(
                update(AgentRunModel)
                .where(AgentRunModel.status.in_(ACTIVE_RUN_STATUSES))
                .values(
                    status=RUN_FAILED,
                    error_code="interrupted",
                    error_detail="The server restarted while this run was active.",
                    finished_at=now,
                )
            )
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["AgentRepository"]
