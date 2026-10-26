"""SQLAlchemy persistence for the append-only agent transcript.

Every write opens its own short session and transaction. This is deliberate: the
SSE turn loop must not hold a request-scoped session for the lifetime of the
stream. Each append transaction reserves one ``agent_commit_seq`` value and uses
it for every entry written in that transaction.

The repository is bound to exactly one account. Every short transaction runs as
``apsor_app`` with the owner's RLS context, and every request-path query also
carries an explicit ``user_id`` predicate. A repository instance must never be
reused for another account. The startup recovery classmethod is the only
cross-user operation and uses a privileged maintenance session.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.agent.domain.agent_domain import (
    ACTIVE_RUN_STATUSES,
    CONVERSATION_ACTIVE,
    CONVERSATION_ARCHIVED,
    KIND_PAGE_CONTEXT,
    KIND_SYSTEM,
    KIND_TOOL_RESULT,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_RUNNING,
    RUN_WAITING,
    TERMINAL_RUN_STATUSES,
    ApprovalDraft,
    EntryDraft,
)
from app.module.agent.exception.domain_error import (
    AgentApprovalNotFoundError,
    AgentApprovalNotPendingError,
    AgentApprovalOutOfOrderError,
    AgentConversationArchivedError,
    AgentConversationBusyError,
    AgentConversationNotFoundError,
    AgentForkEntryInvalidError,
    AgentRequestDuplicateError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
)
from app.module.agent.model.agent_model import (
    AGENT_COMMIT_SEQUENCE,
    AgentApprovalModel,
    AgentConversationModel,
    AgentEntryModel,
    AgentRunModel,
)


class AgentRepository:
    """Repository bound to one account, with one transaction per mutation."""

    def __init__(self, database: Database, *, user_id: int, role: str) -> None:
        self.database = database
        self.user_id = user_id
        self.role = role

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        """Open one owner-scoped transaction; the helper owns commit/rollback."""
        async with self.database.user_session(self.user_id, self.role) as session:
            yield session

    @asynccontextmanager
    async def _read(self) -> AsyncIterator[AsyncSession]:
        """Open one owner-scoped read transaction."""
        async with self.database.user_session(self.user_id, self.role) as session:
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
        *,
        user_id: int,
        conversation_id: int,
    ) -> AgentConversationModel:
        statement = (
            select(AgentConversationModel)
            .where(
                AgentConversationModel.id == conversation_id,
                AgentConversationModel.user_id == user_id,
            )
            .with_for_update()
        )
        conversation = (await session.execute(statement)).scalar_one_or_none()
        if conversation is None or conversation.deleted_at is not None:
            raise AgentConversationNotFoundError(conversation_id)
        return conversation

    @staticmethod
    async def _lock_active_run(
        session: AsyncSession,
        *,
        user_id: int,
        conversation_id: int,
        run_id: int,
    ) -> AgentRunModel:
        statement = (
            select(AgentRunModel)
            .where(
                AgentRunModel.id == run_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.user_id == user_id,
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
                user_id=self.user_id,
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
                user_id=self.user_id,
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

    async def fork_conversation(
        self,
        source_id: int,
        *,
        at_entry_id: int | None,
        title: str,
        provider_session_id: UUID,
        now: datetime,
    ) -> AgentConversationModel:
        """Copy the source transcript through an inclusive cutoff.

        The source conversation and its entries are never changed. Runs are
        operational state and are deliberately not copied, so copied entries
        have ``by_run_id=None`` and start a fresh run history. Head markers and
        context edits are remapped to the copied entry ids; references outside
        the copied range are dropped.
        """
        async with self._transaction() as session:
            source = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=source_id,
            )
            if source.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(source_id)

            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == source_id,
                    AgentRunModel.user_id == self.user_id,
                    AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                )
                .limit(1)
            )
            if active.scalar_one_or_none() is not None:
                raise AgentConversationBusyError(source_id)

            cutoff_entry_id = await self._resolve_fork_cutoff(
                session,
                user_id=self.user_id,
                conversation_id=source_id,
                at_entry_id=at_entry_id,
            )
            statement = (
                select(AgentEntryModel)
                .where(
                    AgentEntryModel.conversation_id == source_id,
                    AgentEntryModel.user_id == self.user_id,
                    AgentEntryModel.id <= cutoff_entry_id,
                )
                .order_by(AgentEntryModel.id.asc())
            )
            source_entries = list((await session.execute(statement)).scalars().all())

            forked = AgentConversationModel(
                user_id=self.user_id,
                parent_conversation_id=source.id,
                fork_at_entry_id=cutoff_entry_id,
                title=title,
                provider=source.provider,
                model=source.model,
                provider_session_id=provider_session_id,
                status=CONVERSATION_ACTIVE,
                created_at=now,
                updated_at=now,
                last_entry_at=now,
            )
            session.add(forked)
            await session.flush()

            copies: list[tuple[AgentEntryModel, AgentEntryModel]] = []
            for source_entry in source_entries:
                commit_seq = await self._next_commit_seq(session)
                copy = AgentEntryModel(
                    user_id=self.user_id,
                    conversation_id=forked.id,
                    commit_seq=commit_seq,
                    kind=source_entry.kind,
                    model=deepcopy(source_entry.model),
                    data=deepcopy(source_entry.data),
                    by_run_id=None,
                    created_at=source_entry.created_at,
                )
                session.add(copy)
                copies.append((source_entry, copy))
            await session.flush()

            id_map = {source_entry.id: copy.id for source_entry, copy in copies}
            for source_entry, copy in copies:
                copy.head_entry_id = (
                    id_map.get(source_entry.head_entry_id)
                    if source_entry.head_entry_id is not None
                    else None
                )
                edited = _remap_edits(source_entry.edits, id_map)
                if edited is not None:
                    copy.edits = edited
            await session.flush()
            return forked

    @staticmethod
    async def _resolve_fork_cutoff(
        session: AsyncSession,
        *,
        user_id: int,
        conversation_id: int,
        at_entry_id: int | None,
    ) -> int:
        if at_entry_id is None:
            latest = await session.execute(
                select(func.max(AgentEntryModel.id)).where(
                    AgentEntryModel.conversation_id == conversation_id,
                    AgentEntryModel.user_id == user_id,
                )
            )
            cutoff_entry_id = latest.scalar_one_or_none()
            if cutoff_entry_id is None:
                raise AgentForkEntryInvalidError(conversation_id, 0)
            return int(cutoff_entry_id)

        statement = select(AgentEntryModel).where(
            AgentEntryModel.id == at_entry_id,
            AgentEntryModel.conversation_id == conversation_id,
            AgentEntryModel.user_id == user_id,
        )
        entry = (await session.execute(statement)).scalar_one_or_none()
        if entry is None:
            raise AgentForkEntryInvalidError(conversation_id, at_entry_id)
        return entry.id

    async def get_conversation(
        self,
        conversation_id: int,
        *,
        include_deleted: bool = False,
    ) -> AgentConversationModel | None:
        async with self._read() as session:
            statement = select(AgentConversationModel).where(
                AgentConversationModel.id == conversation_id,
                AgentConversationModel.user_id == self.user_id,
            )
            conversation = (await session.execute(statement)).scalar_one_or_none()
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
                AgentConversationModel.user_id == self.user_id,
                AgentConversationModel.deleted_at.is_(None),
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
            statement = (
                select(func.count())
                .select_from(AgentConversationModel)
                .where(
                    AgentConversationModel.user_id == self.user_id,
                    AgentConversationModel.deleted_at.is_(None),
                )
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
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            if title is not None:
                conversation.title = title
            if status is not None:
                if status == CONVERSATION_ARCHIVED and conversation.status != CONVERSATION_ARCHIVED:
                    conversation.archived_at = now
                    # Archiving fails closed: no pending write may survive, and
                    # no active run may keep the conversation busy.
                    await session.execute(
                        update(AgentApprovalModel)
                        .where(
                            AgentApprovalModel.conversation_id == conversation_id,
                            AgentApprovalModel.user_id == self.user_id,
                            AgentApprovalModel.status == "pending",
                        )
                        .values(status="expired", resolved_at=now)
                    )
                    await session.execute(
                        update(AgentRunModel)
                        .where(
                            AgentRunModel.conversation_id == conversation_id,
                            AgentRunModel.user_id == self.user_id,
                            AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                        )
                        .values(
                            status=RUN_CANCELLED,
                            abort_requested=True,
                            error_code="aborted",
                            error_detail="The conversation was archived.",
                            finished_at=now,
                        )
                    )
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
                .where(
                    AgentConversationModel.id == conversation_id,
                    AgentConversationModel.user_id == self.user_id,
                )
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
                update(AgentApprovalModel)
                .where(
                    AgentApprovalModel.conversation_id == conversation_id,
                    AgentApprovalModel.user_id == self.user_id,
                    AgentApprovalModel.status == "pending",
                )
                .values(status="expired", resolved_at=now)
            )
            await session.execute(
                update(AgentRunModel)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.user_id == self.user_id,
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
        compaction_draft: EntryDraft | None,
        page_context_draft: EntryDraft | None,
        page_context_key: str | None,
        request_id: str | None,
        now: datetime,
    ) -> tuple[
        AgentConversationModel,
        AgentEntryModel,
        AgentRunModel,
        AgentEntryModel | None,
        AgentEntryModel | None,
    ]:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation_id)

            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.user_id == self.user_id,
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
                        AgentRunModel.user_id == self.user_id,
                        AgentRunModel.request_id == request_id,
                    )
                    .limit(1)
                )
                if duplicate.scalar_one_or_none() is not None:
                    raise AgentRequestDuplicateError(request_id)

            commit_seq = await self._next_commit_seq(session)
            compaction_entry: AgentEntryModel | None = None
            if compaction_draft is not None:
                compaction_entry = await self._append_boundary_entry(
                    session,
                    user_id=self.user_id,
                    conversation_id=conversation_id,
                    commit_seq=commit_seq,
                    draft=compaction_draft,
                    now=now,
                )

            page_context_entry: AgentEntryModel | None = None
            if page_context_draft is not None and page_context_key is not None:
                boundary_id = await self._active_boundary_id(
                    session,
                    user_id=self.user_id,
                    conversation_id=conversation_id,
                )
                previous_statement = select(AgentEntryModel.data).where(
                    AgentEntryModel.conversation_id == conversation_id,
                    AgentEntryModel.user_id == self.user_id,
                    AgentEntryModel.kind == KIND_PAGE_CONTEXT,
                )
                if boundary_id is not None:
                    previous_statement = previous_statement.where(AgentEntryModel.id >= boundary_id)
                previous = await session.execute(
                    previous_statement.order_by(AgentEntryModel.id.desc()).limit(1)
                )
                previous_data = previous.scalar_one_or_none()
                previous_key = (
                    previous_data.get("page_key") if isinstance(previous_data, dict) else None
                )
                if previous_key != page_context_key:
                    page_context_entry = AgentEntryModel(
                        user_id=self.user_id,
                        conversation_id=conversation_id,
                        commit_seq=commit_seq,
                        kind=page_context_draft.kind,
                        model=page_context_draft.messages,
                        data=page_context_draft.data,
                        created_at=now,
                    )
                    session.add(page_context_entry)
                    await session.flush()

            entry = AgentEntryModel(
                user_id=self.user_id,
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
                user_id=self.user_id,
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
            if page_context_entry is not None:
                page_context_entry.by_run_id = run.id
            if compaction_entry is not None:
                compaction_entry.by_run_id = run.id
            conversation.last_entry_at = entry.created_at
            await session.flush()
            return (
                conversation,
                entry,
                run,
                page_context_entry,
                compaction_entry,
            )

    async def append_boundary_entry(
        self,
        *,
        conversation_id: int,
        draft: EntryDraft,
        now: datetime,
    ) -> AgentEntryModel:
        """Append one standalone compaction/reset boundary and activate it."""
        async with self._transaction() as session:
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation_id)
            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.user_id == self.user_id,
                    AgentRunModel.status.in_(ACTIVE_RUN_STATUSES),
                )
                .limit(1)
            )
            if active.scalar_one_or_none() is not None:
                raise AgentConversationBusyError(conversation_id)

            commit_seq = await self._next_commit_seq(session)
            entry = await self._append_boundary_entry(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
                commit_seq=commit_seq,
                draft=draft,
                now=now,
            )
            conversation.last_entry_at = entry.created_at
            return entry

    @staticmethod
    async def _append_boundary_entry(
        session: AsyncSession,
        *,
        user_id: int,
        conversation_id: int,
        commit_seq: int,
        draft: EntryDraft,
        now: datetime,
    ) -> AgentEntryModel:
        """Insert a boundary entry and point its head at itself.

        The self-head starts a new active context and KV-cache lineage while
        leaving every earlier transcript row untouched.
        """
        entry = AgentEntryModel(
            user_id=user_id,
            conversation_id=conversation_id,
            commit_seq=commit_seq,
            kind=draft.kind,
            model=draft.messages,
            data=draft.data,
            created_at=now,
        )
        session.add(entry)
        await session.flush()
        entry.head_entry_id = entry.id
        await session.flush()
        return entry

    @staticmethod
    async def _active_boundary_id(
        session: AsyncSession,
        *,
        user_id: int,
        conversation_id: int,
    ) -> int | None:
        """Return the head id from the newest boundary marker, if any."""
        statement = (
            select(AgentEntryModel.head_entry_id)
            .where(
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.user_id == user_id,
                AgentEntryModel.head_entry_id.is_not(None),
            )
            .order_by(AgentEntryModel.id.desc())
            .limit(1)
        )
        return (await session.execute(statement)).scalar_one_or_none()

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
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation_id)
            active = await session.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.user_id == self.user_id,
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
                        AgentRunModel.user_id == self.user_id,
                        AgentRunModel.request_id == request_id,
                    )
                    .limit(1)
                )
                if duplicate.scalar_one_or_none() is not None:
                    raise AgentRequestDuplicateError(request_id)
            run = AgentRunModel(
                user_id=self.user_id,
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
        usage: dict[str, int] | None = None,
    ) -> AgentEntryModel:
        async with self._transaction() as session:
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            run = await self._lock_active_run(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
                run_id=run_id,
            )
            commit_seq = await self._next_commit_seq(session)
            entry = AgentEntryModel(
                user_id=self.user_id,
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
            if usage is not None:
                prompt_tokens = _usage_int(usage, "prompt_tokens")
                completion_tokens = _usage_int(usage, "completion_tokens")
                run.prompt_tokens += prompt_tokens
                run.completion_tokens += completion_tokens
                run.total_tokens += (
                    _usage_int(usage, "total_tokens") or prompt_tokens + completion_tokens
                )
                run.cached_tokens += _usage_int(usage, "prompt_cache_hit_tokens")
                run.api_calls += 1
            run.last_entry_id = entry.id
            conversation.last_entry_at = entry.created_at
            await session.flush()
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
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            run = await self._lock_active_run(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
                run_id=run_id,
            )
            commit_seq = await self._next_commit_seq(session)
            entries: list[AgentEntryModel] = []
            for draft in drafts:
                entry = AgentEntryModel(
                    user_id=self.user_id,
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

    async def pause_run_with_approvals(
        self,
        *,
        conversation_id: int,
        run_id: int,
        result_drafts: list[EntryDraft],
        approval_drafts: list[ApprovalDraft],
        last_entry_id: int | None,
        now: datetime,
    ) -> tuple[list[AgentEntryModel], list[AgentApprovalModel]]:
        """Append safe tool results, persist pending approvals, and wait.

        The assistant tool-call entry is already durable. Confirmation-required
        calls deliberately have no result yet; the approved or rejected result is
        appended later by :meth:`record_approval_result`.
        """
        if not approval_drafts:
            raise ValueError("pause_run_with_approvals requires at least one approval")
        async with self._transaction() as session:
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            run = await self._lock_active_run(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
                run_id=run_id,
            )
            commit_seq = await self._next_commit_seq(session)
            entries: list[AgentEntryModel] = []
            for draft in result_drafts:
                entry = AgentEntryModel(
                    user_id=self.user_id,
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

            approvals: list[AgentApprovalModel] = []
            for approval_draft in approval_drafts:
                approval = AgentApprovalModel(
                    user_id=self.user_id,
                    conversation_id=conversation_id,
                    run_id=run.id,
                    tool_call_id=approval_draft.tool_call_id,
                    tool_name=approval_draft.tool_name,
                    status="pending",
                    arguments=approval_draft.arguments,
                    preview=approval_draft.preview,
                    resume_state=approval_draft.resume_state,
                    requested_at=now,
                    created_at=now,
                )
                session.add(approval)
                approvals.append(approval)
            await session.flush()

            run.status = RUN_WAITING
            if entries:
                run.last_entry_id = entries[-1].id
                conversation.last_entry_at = entries[-1].created_at
            elif last_entry_id is not None:
                run.last_entry_id = last_entry_id
            return entries, approvals

    async def list_approvals(
        self,
        conversation_id: int,
        *,
        status: str | None,
    ) -> list[AgentApprovalModel]:
        async with self._read() as session:
            statement = select(AgentApprovalModel).where(
                AgentApprovalModel.conversation_id == conversation_id,
                AgentApprovalModel.user_id == self.user_id,
            )
            if status is not None:
                statement = statement.where(AgentApprovalModel.status == status)
            statement = statement.order_by(AgentApprovalModel.id.asc())
            return list((await session.execute(statement)).scalars().all())

    async def get_approval(self, approval_id: int) -> AgentApprovalModel | None:
        async with self._read() as session:
            statement = select(AgentApprovalModel).where(
                AgentApprovalModel.id == approval_id,
                AgentApprovalModel.user_id == self.user_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def list_pending_approvals(self, run_id: int) -> list[AgentApprovalModel]:
        async with self._read() as session:
            statement = (
                select(AgentApprovalModel)
                .where(
                    AgentApprovalModel.run_id == run_id,
                    AgentApprovalModel.user_id == self.user_id,
                    AgentApprovalModel.status == "pending",
                )
                .order_by(AgentApprovalModel.id.asc())
            )
            return list((await session.execute(statement)).scalars().all())

    async def claim_approval(
        self,
        *,
        approval_id: int,
        approved: bool,
        now: datetime,
    ) -> tuple[AgentApprovalModel, AgentRunModel, AgentConversationModel]:
        """Claim one pending approval exactly once.

        Resolution requires the earliest pending approval for the run, so a
        multi-call batch always appends tool results in source order.
        """
        async with self._transaction() as session:
            approval = (
                await session.execute(
                    select(AgentApprovalModel)
                    .where(
                        AgentApprovalModel.id == approval_id,
                        AgentApprovalModel.user_id == self.user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if approval is None:
                raise AgentApprovalNotFoundError(approval_id)
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=approval.conversation_id,
            )
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation.id)
            if approval.status != "pending":
                raise AgentApprovalNotPendingError(approval.status)

            run = (
                await session.execute(
                    select(AgentRunModel)
                    .where(
                        AgentRunModel.id == approval.run_id,
                        AgentRunModel.conversation_id == approval.conversation_id,
                        AgentRunModel.user_id == self.user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if run is None:
                raise AgentRunNotFoundError(approval.run_id)
            if run.status != RUN_WAITING or run.abort_requested:
                raise AgentApprovalNotPendingError(run.status)

            earliest = (
                await session.execute(
                    select(func.min(AgentApprovalModel.id)).where(
                        AgentApprovalModel.run_id == run.id,
                        AgentApprovalModel.user_id == self.user_id,
                        AgentApprovalModel.status == "pending",
                    )
                )
            ).scalar_one_or_none()
            if earliest != approval.id:
                raise AgentApprovalOutOfOrderError()

            approval.status = "approved" if approved else "rejected"
            approval.resolved_at = now
            return approval, run, conversation

    async def record_approval_result(
        self,
        *,
        approval_id: int,
        draft: EntryDraft,
        now: datetime,
    ) -> tuple[
        AgentEntryModel,
        AgentRunModel,
        AgentConversationModel,
        list[AgentApprovalModel],
    ]:
        """Append the resolved tool result and resume when no approvals remain."""
        async with self._transaction() as session:
            approval = (
                await session.execute(
                    select(AgentApprovalModel)
                    .where(
                        AgentApprovalModel.id == approval_id,
                        AgentApprovalModel.user_id == self.user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if approval is None:
                raise AgentApprovalNotFoundError(approval_id)
            conversation = await self._lock_conversation(
                session,
                user_id=self.user_id,
                conversation_id=approval.conversation_id,
            )
            if conversation.status != CONVERSATION_ACTIVE:
                raise AgentConversationArchivedError(conversation.id)
            if (
                approval.status not in {"approved", "rejected"}
                or approval.resolved_by_entry_id is not None
            ):
                raise AgentApprovalNotPendingError(approval.status)

            run = (
                await session.execute(
                    select(AgentRunModel)
                    .where(
                        AgentRunModel.id == approval.run_id,
                        AgentRunModel.conversation_id == approval.conversation_id,
                        AgentRunModel.user_id == self.user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if run is None:
                raise AgentRunNotFoundError(approval.run_id)
            if run.status != RUN_WAITING:
                raise AgentApprovalNotPendingError(run.status)

            commit_seq = await self._next_commit_seq(session)
            entry = AgentEntryModel(
                user_id=self.user_id,
                conversation_id=approval.conversation_id,
                commit_seq=commit_seq,
                kind=KIND_TOOL_RESULT,
                model=draft.messages,
                data=draft.data,
                by_run_id=run.id,
                created_at=now,
            )
            session.add(entry)
            await session.flush()
            approval.resolved_by_entry_id = entry.id
            run.last_entry_id = entry.id
            conversation.last_entry_at = entry.created_at

            remaining = list(
                (
                    await session.execute(
                        select(AgentApprovalModel)
                        .where(
                            AgentApprovalModel.run_id == run.id,
                            AgentApprovalModel.user_id == self.user_id,
                            AgentApprovalModel.status == "pending",
                        )
                        .order_by(AgentApprovalModel.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            if not remaining:
                run.status = RUN_RUNNING
            return entry, run, conversation, remaining

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
                    AgentRunModel.user_id == self.user_id,
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
            statement = select(AgentRunModel).where(
                AgentRunModel.id == run_id,
                AgentRunModel.user_id == self.user_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def get_latest_run(self, conversation_id: int) -> AgentRunModel | None:
        async with self._read() as session:
            statement = (
                select(AgentRunModel)
                .where(
                    AgentRunModel.conversation_id == conversation_id,
                    AgentRunModel.user_id == self.user_id,
                )
                .order_by(AgentRunModel.id.desc())
                .limit(1)
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def get_entry(self, entry_id: int) -> AgentEntryModel | None:
        async with self._read() as session:
            statement = select(AgentEntryModel).where(
                AgentEntryModel.id == entry_id,
                AgentEntryModel.user_id == self.user_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def latest_entry_id(self, conversation_id: int) -> int | None:
        async with self._read() as session:
            statement = select(func.max(AgentEntryModel.id)).where(
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.user_id == self.user_id,
            )
            return (await session.execute(statement)).scalar_one_or_none()

    async def list_run_entries(self, run_id: int) -> list[AgentEntryModel]:
        async with self._read() as session:
            statement = (
                select(AgentEntryModel)
                .where(
                    AgentEntryModel.by_run_id == run_id,
                    AgentEntryModel.user_id == self.user_id,
                )
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
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.user_id == self.user_id,
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
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.user_id == self.user_id,
            )
            if after_id is not None:
                statement = statement.where(AgentEntryModel.id > after_id)
            statement = statement.order_by(AgentEntryModel.id.asc()).limit(limit + 1)
            rows = list((await session.execute(statement)).scalars().all())
            has_more = len(rows) > limit
            return rows[:limit], has_more

    async def count_entries(self, conversation_id: int) -> int:
        async with self._read() as session:
            statement = (
                select(func.count())
                .select_from(AgentEntryModel)
                .where(
                    AgentEntryModel.conversation_id == conversation_id,
                    AgentEntryModel.user_id == self.user_id,
                )
            )
            return int((await session.execute(statement)).scalar_one())

    async def last_page_context_key(self, conversation_id: int) -> str | None:
        async with self._read() as session:
            boundary_id = await self._active_boundary_id(
                session,
                user_id=self.user_id,
                conversation_id=conversation_id,
            )
            statement = select(AgentEntryModel.data).where(
                AgentEntryModel.conversation_id == conversation_id,
                AgentEntryModel.user_id == self.user_id,
                AgentEntryModel.kind == KIND_PAGE_CONTEXT,
            )
            if boundary_id is not None:
                statement = statement.where(AgentEntryModel.id >= boundary_id)
            statement = statement.order_by(AgentEntryModel.id.desc()).limit(1)
            data = (await session.execute(statement)).scalar_one_or_none()
            if not isinstance(data, dict):
                return None
            key = data.get("page_key")
            return key if isinstance(key, str) and key else None

    async def is_abort_requested(self, conversation_id: int, run_id: int) -> bool:
        async with self._read() as session:
            statement = select(AgentRunModel.status, AgentRunModel.abort_requested).where(
                AgentRunModel.id == run_id,
                AgentRunModel.conversation_id == conversation_id,
                AgentRunModel.user_id == self.user_id,
            )
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return True
            status, abort_requested = row
            return bool(abort_requested) or status in TERMINAL_RUN_STATUSES

    @classmethod
    async def recover_stale_runs(cls, database: Database, *, now: datetime) -> int:
        """Recover runs orphaned by an API restart across every account.

        This is startup maintenance, not request work: it intentionally uses the
        privileged owner session because no user context exists before serving.
        User-scoped repositories do not expose recovery.

        A stale ``running`` run failed mid-flight and is marked ``failed`` with
        ``interrupted``. A ``waiting`` run is resumable only while it still has a
        valid pending approval; otherwise it fails closed with a readable
        ``approval_orphaned`` error. Pending approvals on terminal runs or
        inactive conversations are expired.
        """
        async with database.maintenance_session() as session:
            await session.execute(
                text(
                    """
                    UPDATE agent_approval AS approval
                    SET status = 'expired', resolved_at = :now
                    WHERE approval.status = 'pending'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM agent_run AS run
                          JOIN agent_conversation AS conversation
                            ON conversation.id = run.conversation_id
                          WHERE run.id = approval.run_id
                            AND run.status = 'waiting'
                            AND conversation.status = 'active'
                            AND conversation.deleted_at IS NULL
                      )
                    """
                ),
                {"now": now},
            )
            interrupted = await session.execute(
                update(AgentRunModel)
                .where(AgentRunModel.status == RUN_RUNNING)
                .values(
                    status=RUN_FAILED,
                    error_code="interrupted",
                    error_detail="The server restarted while this run was active.",
                    finished_at=now,
                )
            )
            orphaned = 0
            waiting_runs = list(
                (
                    await session.execute(
                        select(AgentRunModel)
                        .where(AgentRunModel.status == RUN_WAITING)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            for run in waiting_runs:
                pending = (
                    await session.execute(
                        select(func.count())
                        .select_from(AgentApprovalModel)
                        .where(
                            AgentApprovalModel.run_id == run.id,
                            AgentApprovalModel.status == "pending",
                        )
                    )
                ).scalar_one()
                if int(pending) > 0:
                    continue
                run.status = RUN_FAILED
                run.error_code = "approval_orphaned"
                run.error_detail = (
                    "The run was waiting for approval, but no valid pending approval was found."
                )
                run.finished_at = now
                orphaned += 1
            return int(getattr(interrupted, "rowcount", 0) or 0) + orphaned


def _remap_edits(
    raw: object,
    id_map: dict[int, int],
) -> list[dict[str, Any]] | None:
    """Remap context-edit targets and drop references outside the fork range."""
    if not isinstance(raw, list):
        return None
    remapped: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        target = item.get("target_entry_id")
        if not isinstance(target, int) or isinstance(target, bool):
            continue
        mapped = id_map.get(target)
        if mapped is None:
            continue
        remapped.append({**deepcopy(item), "target_entry_id": mapped})
    return remapped or None


def _usage_int(usage: dict[str, int], key: str) -> int:
    """Read one bounded, non-negative token counter from provider usage."""
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return min(max(0, value), 10**15)


__all__ = ["AgentRepository"]
