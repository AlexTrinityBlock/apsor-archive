"""Consumer-owned persistence contract for the agent service."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.module.agent.domain.agent_domain import EntryDraft
from app.module.agent.model.agent_model import (
    AgentConversationModel,
    AgentEntryModel,
    AgentRunModel,
)


class AgentRepositoryProtocol(Protocol):
    """One writer per conversation, one commit sequence per transaction."""

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
    ) -> tuple[AgentConversationModel, AgentEntryModel]: ...

    async def get_conversation(
        self,
        conversation_id: int,
        *,
        include_deleted: bool = False,
    ) -> AgentConversationModel | None: ...

    async def list_conversations(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[AgentConversationModel]: ...

    async def count_conversations(self, *, status: str | None) -> int: ...

    async def update_conversation(
        self,
        conversation_id: int,
        *,
        title: str | None,
        status: str | None,
        now: datetime,
    ) -> AgentConversationModel | None: ...

    async def soft_delete_conversation(
        self,
        conversation_id: int,
        *,
        now: datetime,
    ) -> bool: ...

    async def append_user_and_run(
        self,
        *,
        conversation_id: int,
        draft: EntryDraft,
        request_id: str | None,
        now: datetime,
    ) -> tuple[AgentConversationModel, AgentEntryModel, AgentRunModel]: ...

    async def create_run(
        self,
        *,
        conversation_id: int,
        user_entry_id: int,
        last_entry_id: int,
        request_id: str | None,
        now: datetime,
    ) -> AgentRunModel: ...

    async def append_assistant(
        self,
        *,
        conversation_id: int,
        run_id: int,
        draft: EntryDraft,
        now: datetime,
    ) -> AgentEntryModel: ...

    async def append_tool_results(
        self,
        *,
        conversation_id: int,
        run_id: int,
        drafts: list[EntryDraft],
        now: datetime,
    ) -> list[AgentEntryModel]: ...

    async def complete_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        last_entry_id: int | None,
        now: datetime,
    ) -> None: ...

    async def fail_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        error_code: str,
        error_detail: str,
        last_entry_id: int | None,
        now: datetime,
    ) -> None: ...

    async def cancel_run(
        self,
        *,
        conversation_id: int,
        run_id: int,
        last_entry_id: int | None,
        now: datetime,
    ) -> None: ...

    async def get_run(self, run_id: int) -> AgentRunModel | None: ...

    async def get_latest_run(self, conversation_id: int) -> AgentRunModel | None: ...

    async def get_entry(self, entry_id: int) -> AgentEntryModel | None: ...

    async def latest_entry_id(self, conversation_id: int) -> int | None: ...

    async def list_run_entries(self, run_id: int) -> list[AgentEntryModel]: ...

    async def load_context_entries(
        self,
        conversation_id: int,
        *,
        cutoff_entry_id: int | None,
    ) -> list[AgentEntryModel]: ...

    async def list_entries(
        self,
        conversation_id: int,
        *,
        after_id: int | None,
        limit: int,
    ) -> tuple[list[AgentEntryModel], bool]: ...

    async def count_entries(self, conversation_id: int) -> int: ...

    async def is_abort_requested(self, conversation_id: int, run_id: int) -> bool: ...

    async def mark_interrupted_runs(self, *, now: datetime) -> int: ...
