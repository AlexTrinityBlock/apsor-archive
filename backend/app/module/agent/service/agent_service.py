"""Conversation orchestration, the Pi-shaped tool loop, and SSE turn events."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.domain.agent_domain import (
    ERROR_FINISH_REASONS,
    KIND_ASSISTANT,
    KIND_PAGE_CONTEXT,
    KIND_RESET,
    KIND_TOOL_RESULT,
    KIND_USER,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_WAITING,
    AgentStreamEvent,
    ApprovalDraft,
    EntryDraft,
    ProviderContext,
    ToolOutcome,
    TranscriptEntry,
    parse_edits,
)
from app.module.agent.domain.compaction_domain import (
    build_compaction_draft,
    compactable_context_entries,
    estimate_context_tokens,
)
from app.module.agent.domain.context_domain import build_context, render_tool_result
from app.module.agent.domain.owner_profile_domain import OwnerProfile
from app.module.agent.domain.tool_catalog import PROMPT_VERSION, TOOLS_VERSION
from app.module.agent.domain.xml_domain import attributes, clip, xml_text
from app.module.agent.exception.domain_error import (
    AgentApprovalNotFoundError,
    AgentConversationArchivedError,
    AgentConversationNotFoundError,
    AgentInvalidEntryError,
    AgentNotConfiguredError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
    AgentRunNotRetryableError,
)
from app.module.agent.model.agent_model import (
    AgentApprovalModel,
    AgentConversationModel,
    AgentEntryModel,
    AgentRunModel,
)
from app.module.agent.protocol.agent_repository_protocol import AgentRepositoryProtocol
from app.module.agent.protocol.chat_generator_protocol import (
    ChatGeneratorProtocol,
    ChatResult,
    ChatToolCall,
)
from app.module.agent.schema.agent_schema import (
    AgentApprovalSchema,
    AgentConversationCreateSchema,
    AgentConversationDetailSchema,
    AgentConversationForkSchema,
    AgentConversationPatchSchema,
    AgentConversationSchema,
    AgentEntryPageSchema,
    AgentEntrySchema,
    AgentMessageCreateSchema,
    AgentPageContextSchema,
    AgentRetrySchema,
    AgentRunSchema,
    AgentToolCatalogSchema,
    AgentToolSchema,
    AgentTurnResultSchema,
)
from app.module.agent.service.system_prompt import build_system_data, build_system_model
from app.module.agent.service.system_prompt_service import SystemPromptService
from app.module.agent.service.time_context import current_time_block
from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.knowledge.exception.domain_error import AiNotConfiguredError
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"\[(?:file|memory|summary):\d+(?:#\d+)?\]")
_PAGE_CONTEXT_LINE_WS = re.compile(r"[ \t\f\v]+")
_PAGE_CONTEXT_BLANK_LINES = re.compile(r"\n{3,}")
LIMIT_CODES = frozenset(
    {"step_limit", "token_limit", "tool_call_limit", "tool_result_budget_exhausted"}
)


@dataclass(frozen=True)
class AgentTurnState:
    """The durable state needed to run one assistant turn."""

    conversation: AgentConversationSchema
    run: AgentRunSchema
    user_entry: AgentEntrySchema
    cutoff_entry_id: int
    page_context_entry_id: int | None = None


@dataclass(frozen=True)
class AgentApprovalTurn:
    """A resolved approval plus the loop snapshot used to resume its run."""

    turn: AgentTurnState
    approval: AgentApprovalSchema
    call: ChatToolCall
    outcome: ToolOutcome
    tool_entry: AgentEntrySchema
    remaining: list[AgentApprovalSchema]
    resume_state: dict[str, Any]


@dataclass
class _CompletionOutcome:
    """Mutable holder for an async-generator completion."""

    result: ChatResult | None = None
    error: Exception | None = None


class AgentService:
    """Own conversation CRUD and the durable multi-step turn loop.

    Provider and model selection come from the existing database-backed AI
    runtime settings (``/api/v1/settings/ai``). Run-loop limits come from the
    immutable ``AgentRuntimeConfig`` snapshot passed by the dependency. A new
    request loads a fresh snapshot, while an already running SSE stream keeps the
    snapshot it started with.
    """

    def __init__(
        self,
        *,
        repository: AgentRepositoryProtocol,
        chat_generator: ChatGeneratorProtocol,
        tool_registry: AgentToolRegistry,
        default_provider: str,
        default_model: str,
        config: AgentRuntimeConfig,
        system_prompt_service: SystemPromptService,
        server_timezone: str = "Asia/Taipei",
    ) -> None:
        self.repository = repository
        self.chat_generator = chat_generator
        self.tool_registry = tool_registry
        self.default_provider = default_provider
        self.default_model = default_model
        self.config = config
        self.system_prompt_service = system_prompt_service
        self.server_timezone = server_timezone

    async def create_conversation(
        self,
        payload: AgentConversationCreateSchema,
        *,
        owner_profile: OwnerProfile | None = None,
    ) -> AgentConversationSchema:
        provider = payload.provider or self.default_provider
        if provider not in {"deepseek", "openai-compatible"}:
            provider = "deepseek"
        model = payload.model or self.default_model or "deepseek-flash"
        now = utcnow()
        custom_sections, builtin_sections = await self.system_prompt_service.get_active_sections()
        system_data = build_system_data(
            provider=provider,
            model=model,
            custom_sections=custom_sections,
            builtin_sections=builtin_sections,
            owner_profile=owner_profile,
        )
        system_model = build_system_model(system_data)
        conversation, _entry = await self.repository.create_conversation(
            title=payload.title or "New conversation",
            provider=provider,
            model=model,
            provider_session_id=uuid4(),
            system_model=system_model,
            system_data=system_data,
            now=now,
        )
        return _conversation_schema(conversation)

    async def fork_conversation(
        self,
        conversation_id: int,
        payload: AgentConversationForkSchema,
    ) -> AgentConversationSchema:
        """Copy a transcript through an inclusive entry cutoff.

        The new conversation is active, gets a fresh provider session id, and
        owns independent entry rows. Runs and approval state are not copied;
        the next user message starts a new run against the copied context.
        """
        source = await self.repository.get_conversation(conversation_id)
        if source is None:
            raise AgentConversationNotFoundError(conversation_id)
        title = (payload.title or "").strip() or f"Fork of {source.title}"
        title = title[:200]
        forked = await self.repository.fork_conversation(
            source_id=conversation_id,
            at_entry_id=payload.at_entry_id,
            title=title,
            provider_session_id=uuid4(),
            now=utcnow(),
        )
        return _conversation_schema(forked)

    async def list_conversations(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentConversationSchema], int]:
        conversations = await self.repository.list_conversations(
            status=status,
            limit=limit,
            offset=offset,
        )
        total = await self.repository.count_conversations(status=status)
        return [_conversation_schema(item) for item in conversations], total

    async def get_conversation(
        self,
        conversation_id: int,
        *,
        limit: int,
    ) -> AgentConversationDetailSchema:
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        entries, has_more = await self.repository.list_entries(
            conversation_id,
            after_id=None,
            limit=limit,
        )
        total = await self.repository.count_entries(conversation_id)
        page = _entry_page(conversation_id, entries, total, has_more)
        base = _conversation_schema(conversation)
        last_page_context_key = await self.repository.last_page_context_key(conversation_id)
        return AgentConversationDetailSchema(
            **base.model_dump(),
            entries=page.entries,
            entries_total=page.total_results,
            entries_next_after_id=page.next_after_id,
            entries_has_more=page.has_more,
            last_page_context_key=last_page_context_key,
        )

    async def list_entries(
        self,
        conversation_id: int,
        *,
        after_id: int | None,
        limit: int,
    ) -> AgentEntryPageSchema:
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        entries, has_more = await self.repository.list_entries(
            conversation_id,
            after_id=after_id,
            limit=limit,
        )
        total = await self.repository.count_entries(conversation_id)
        return _entry_page(conversation_id, entries, total, has_more)

    async def update_conversation(
        self,
        conversation_id: int,
        payload: AgentConversationPatchSchema,
    ) -> AgentConversationSchema:
        conversation = await self.repository.update_conversation(
            conversation_id,
            title=payload.title,
            status=payload.status,
            now=utcnow(),
        )
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        return _conversation_schema(conversation)

    async def delete_conversation(self, conversation_id: int) -> None:
        deleted = await self.repository.soft_delete_conversation(
            conversation_id,
            now=utcnow(),
        )
        if not deleted:
            raise AgentConversationNotFoundError(conversation_id)

    def tools_catalog(self) -> AgentToolCatalogSchema:
        return AgentToolCatalogSchema(
            prompt_version=PROMPT_VERSION,
            tools_version=TOOLS_VERSION,
            tools=[AgentToolSchema(**item) for item in self.tool_registry.catalog()],
        )

    async def begin_message(
        self,
        conversation_id: int,
        payload: AgentMessageCreateSchema,
    ) -> AgentTurnState:
        """Persist the user entry and running run before any provider call."""
        self._ensure_configured()
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        if conversation.status != "active":
            raise AgentConversationArchivedError(conversation_id)
        content = payload.content.strip()
        if not content:
            raise AgentInvalidEntryError("Message content must not be empty.")
        now = utcnow()
        time_context = current_time_block(
            now=now,
            client_timezone=payload.client_timezone,
            client_utc_offset_minutes=payload.client_utc_offset_minutes,
            server_timezone=self.server_timezone,
        )
        data: dict[str, Any] = {
            "request_id": payload.request_id,
            "client_timezone": payload.client_timezone,
            "client_utc_offset_minutes": payload.client_utc_offset_minutes,
            "time_context": time_context,
        }
        compaction_draft = await self._auto_compaction_draft(conversation_id)
        page_context_draft, page_context_key = _page_context_draft(
            payload.page_context,
            max_chars=self.config.max_page_context_chars,
        )
        (
            conversation_model,
            user_entry,
            run,
            page_context_entry,
            _compaction_entry,
        ) = await self.repository.append_user_and_run(
            conversation_id=conversation_id,
            draft=EntryDraft(
                kind=KIND_USER,
                messages=[{"role": "user", "content": content}],
                data=data,
            ),
            compaction_draft=compaction_draft,
            page_context_draft=page_context_draft,
            page_context_key=page_context_key,
            request_id=payload.request_id,
            now=now,
        )
        return AgentTurnState(
            conversation=_conversation_schema(conversation_model),
            run=_run_schema(run),
            user_entry=_entry_schema(user_entry),
            cutoff_entry_id=user_entry.id,
            page_context_entry_id=(
                page_context_entry.id if page_context_entry is not None else None
            ),
        )

    async def begin_retry(
        self,
        conversation_id: int,
        payload: AgentRetrySchema,
    ) -> AgentTurnState:
        """Create a new run for the latest failed or cancelled user entry."""
        self._ensure_configured()
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        if conversation.status != "active":
            raise AgentConversationArchivedError(conversation_id)
        latest = await self.repository.get_latest_run(conversation_id)
        if latest is None:
            raise AgentRunNotFoundError()
        if latest.status not in {"failed", "cancelled"}:
            raise AgentRunNotRetryableError(latest.status)
        user_entry = await self.repository.get_entry(latest.user_entry_id)
        if user_entry is None:
            raise AgentRunNotFoundError(latest.id)
        last_entry_id = await self.repository.latest_entry_id(conversation_id)
        cutoff_entry_id = last_entry_id or user_entry.id
        run = await self.repository.create_run(
            conversation_id=conversation_id,
            user_entry_id=user_entry.id,
            last_entry_id=cutoff_entry_id,
            request_id=payload.request_id,
            now=utcnow(),
        )
        return AgentTurnState(
            conversation=_conversation_schema(conversation),
            run=_run_schema(run),
            user_entry=_entry_schema(user_entry),
            cutoff_entry_id=cutoff_entry_id,
            page_context_entry_id=None,
        )

    async def compact_conversation(
        self,
        conversation_id: int,
    ) -> AgentEntrySchema:
        """Append a deterministic manual compaction boundary.

        The summary is built from the current active context; no provider call is
        made. The new entry points its head at itself, which starts a new context
        and KV-cache segment without changing any earlier row. An empty active
        context still yields a small explicit entry instead of an error.
        """
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        if conversation.status != "active":
            raise AgentConversationArchivedError(conversation_id)
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=None,
        )
        draft = build_compaction_draft(
            _transcript_from_rows(rows),
            reason="manual",
            auto=False,
            max_summary_chars=self.config.max_compaction_summary_chars,
            max_last_user_chars=self.config.max_compaction_last_user_chars,
        )
        entry = await self.repository.append_boundary_entry(
            conversation_id=conversation_id,
            draft=draft,
            now=utcnow(),
        )
        return _entry_schema(entry)

    async def clear_conversation(self, conversation_id: int) -> AgentEntrySchema:
        """Append a manual reset boundary; the transcript itself is preserved."""
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        if conversation.status != "active":
            raise AgentConversationArchivedError(conversation_id)
        entry = await self.repository.append_boundary_entry(
            conversation_id=conversation_id,
            draft=EntryDraft(
                kind=KIND_RESET,
                messages=[],
                data={"reason": "manual_clear"},
            ),
            now=utcnow(),
        )
        return _entry_schema(entry)

    async def _auto_compaction_draft(
        self,
        conversation_id: int,
    ) -> EntryDraft | None:
        """Return a compaction draft when the active context crosses the limit.

        Auto compaction is skipped for a new/empty conversation and whenever no
        user turn exists in the active segment, because the compacted message
        must carry the last user input.
        """
        if not self.config.auto_compaction_enabled:
            return None
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=None,
        )
        transcript = _transcript_from_rows(rows)
        compactable = compactable_context_entries(transcript)
        if not compactable:
            return None
        if not any(entry.kind == KIND_USER for entry in compactable):
            return None
        if estimate_context_tokens(transcript) <= self.config.compaction_threshold_tokens:
            return None
        return build_compaction_draft(
            transcript,
            reason="auto_context_threshold",
            auto=True,
            max_summary_chars=self.config.max_compaction_summary_chars,
            max_last_user_chars=self.config.max_compaction_last_user_chars,
        )

    async def stream_turn(self, turn: AgentTurnState) -> AsyncIterator[AgentStreamEvent]:
        """Run the model/tool loop and yield transport-only events."""
        async for event in self._run_loop(
            turn,
            start_step=1,
            total_usage={},
            tool_calls_used=0,
            last_entry_id=turn.cutoff_entry_id,
            resumed=False,
            emit_start=True,
        ):
            yield event

    async def _run_loop(
        self,
        turn: AgentTurnState,
        *,
        start_step: int,
        total_usage: dict[str, int],
        tool_calls_used: int,
        last_entry_id: int,
        resumed: bool,
        emit_start: bool,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Continue one durable turn from a deterministic loop snapshot."""
        conversation_id = turn.conversation.id
        run_id = turn.run.id
        terminal = False

        try:
            if emit_start:
                yield AgentStreamEvent(
                    "run_start",
                    {
                        "run_id": run_id,
                        "user_entry_id": turn.user_entry.id,
                        "page_context_entry_id": turn.page_context_entry_id,
                        "page_context_attached": turn.page_context_entry_id is not None,
                        "resumed": resumed,
                    },
                )
            context = await self._context(conversation_id, last_entry_id)

            for step in range(start_step, self.config.max_steps + 1):
                if await self.repository.is_abort_requested(conversation_id, run_id):
                    await self._best_effort_cancel(turn, last_entry_id)
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return

                if _token_total(total_usage) >= self.config.max_total_tokens:
                    last_entry_id = await self._append_failure_assistant(
                        turn,
                        last_entry_id,
                        "token_limit",
                        "The token budget was exhausted.",
                        step,
                    )
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        "token_limit",
                        "The token budget was exhausted.",
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "error",
                        {
                            "code": "token_limit",
                            "detail": "The token budget was exhausted.",
                        },
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                yield AgentStreamEvent(
                    "message_start",
                    {"entry_id": None, "kind": KIND_ASSISTANT, "role": "assistant"},
                )
                completion = _CompletionOutcome()
                async for event in self._completion_events(
                    context,
                    turn.conversation.model,
                    completion,
                ):
                    yield event
                result = completion.result
                provider_error = completion.error
                if result is None:
                    (
                        last_entry_id,
                        provider_code,
                        provider_detail,
                    ) = await self._append_provider_failure(
                        turn,
                        last_entry_id,
                        provider_error,
                        step,
                    )
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        provider_code,
                        provider_detail,
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "message_end",
                        {
                            "entry_id": last_entry_id,
                            "usage": {},
                            "finish_reason": "error",
                        },
                    )
                    yield AgentStreamEvent(
                        "error",
                        {"code": provider_code, "detail": provider_detail},
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                finish_reason = _normalize_finish(result)
                if finish_reason is None:
                    (
                        last_entry_id,
                        provider_code,
                        provider_detail,
                    ) = await self._append_provider_failure(
                        turn,
                        last_entry_id,
                        RuntimeError("truncated or malformed completion"),
                        step,
                    )
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        provider_code,
                        provider_detail,
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "message_end",
                        {
                            "entry_id": last_entry_id,
                            "usage": {},
                            "finish_reason": "error",
                        },
                    )
                    yield AgentStreamEvent(
                        "error",
                        {"code": provider_code, "detail": provider_detail},
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                assistant_message = _assistant_message(result)
                assistant_data = _assistant_data(
                    result,
                    turn,
                    step,
                    finish_reason,
                    context.cache_prefix_hash,
                )
                try:
                    assistant_entry = await self.repository.append_assistant(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        draft=EntryDraft(
                            kind=KIND_ASSISTANT,
                            messages=[assistant_message],
                            data=assistant_data,
                        ),
                        now=utcnow(),
                    )
                except AgentRunNotActiveError:
                    await self._best_effort_cancel(turn, last_entry_id)
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return
                last_entry_id = assistant_entry.id
                _merge_usage(total_usage, result.usage)
                yield AgentStreamEvent(
                    "message_end",
                    {
                        "entry_id": assistant_entry.id,
                        "usage": dict(result.usage),
                        "finish_reason": finish_reason,
                    },
                )

                if not result.tool_calls:
                    await self.repository.complete_run(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        last_entry_id=last_entry_id,
                        now=utcnow(),
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_COMPLETED},
                    )
                    return

                calls = result.tool_calls
                if step >= self.config.max_steps:
                    limit_entries, limit_events = await self._limit_tool_batch(
                        turn,
                        calls,
                        "step_limit",
                        "The step limit was reached before the tool calls could run.",
                    )
                    for event in limit_events:
                        yield event
                    if limit_entries is None:
                        await self._best_effort_cancel(turn, last_entry_id)
                        terminal = True
                        yield AgentStreamEvent(
                            "run_end",
                            {"run_id": run_id, "status": RUN_CANCELLED},
                        )
                        return
                    last_entry_id = limit_entries[-1].id if limit_entries else last_entry_id
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        "step_limit",
                        "The step limit was reached.",
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "error",
                        {"code": "step_limit", "detail": "The step limit was reached."},
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                if _token_total(total_usage) >= self.config.max_total_tokens:
                    limit_entries, limit_events = await self._limit_tool_batch(
                        turn,
                        calls,
                        "token_limit",
                        "The token budget was exhausted before the tool calls could run.",
                    )
                    for event in limit_events:
                        yield event
                    if limit_entries is None:
                        await self._best_effort_cancel(turn, last_entry_id)
                        terminal = True
                        yield AgentStreamEvent(
                            "run_end",
                            {"run_id": run_id, "status": RUN_CANCELLED},
                        )
                        return
                    last_entry_id = limit_entries[-1].id if limit_entries else last_entry_id
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        "token_limit",
                        "The token budget was exhausted.",
                    )
                    terminal = True
                    yield AgentStreamEvent(
                        "error",
                        {
                            "code": "token_limit",
                            "detail": "The token budget was exhausted.",
                        },
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                batch_size = len(calls)
                parallel = self.config.parallel_tools_enabled and batch_size > 1
                planned: list[tuple[ChatToolCall, ToolOutcome] | None] = [None] * batch_size
                eligible_indices: list[int] = []
                approval_specs: list[tuple[int, ChatToolCall, dict[str, Any]]] = []
                backend_approved_indices: set[int] = set()
                for index, call in enumerate(calls):
                    yield AgentStreamEvent(
                        "tool_start",
                        {
                            "entry_id": None,
                            "tool_call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "parallel": parallel,
                            "batch_size": batch_size,
                            "parallel_index": index,
                        },
                    )
                    if tool_calls_used >= self.config.max_tool_calls_per_turn:
                        planned[index] = (
                            call,
                            _limit_outcome(
                                call.name,
                                "tool_call_limit",
                                "The tool-call limit was reached for this turn.",
                            ),
                        )
                        continue
                    tool_calls_used += 1
                    if self.tool_registry.requires_confirmation(call.name):
                        if self.config.save_memory_requires_approval:
                            validated, validation_error = self.tool_registry.validate_arguments(
                                call.name,
                                call.arguments,
                                parse_error=call.parse_error,
                            )
                            if validation_error is not None:
                                planned[index] = (call, validation_error)
                            else:
                                approval_specs.append((index, call, validated or {}))
                            continue
                        # The human gate is disabled for this run snapshot. The
                        # backend authorizes the write itself; a model-supplied
                        # user_confirmed never participates in this decision.
                        backend_approved_indices.add(index)
                    eligible_indices.append(index)

                if eligible_indices:
                    if self.config.parallel_tools_enabled:
                        executed = await self._gather_tools(
                            calls,
                            eligible_indices,
                            backend_approved_indices,
                        )
                    else:
                        executed = []
                        for index in eligible_indices:
                            executed.append(
                                await self._execute_tool(
                                    calls[index],
                                    approved=index in backend_approved_indices,
                                )
                            )
                    for index, outcome in zip(
                        eligible_indices,
                        executed,
                        strict=True,
                    ):
                        planned[index] = (calls[index], outcome)

                # Hard turn limits end the run; pending writes must not outlive a
                # failed run, so confirmation calls receive the same limit result.
                limit_codes = {
                    outcome[1].error_code
                    for outcome in planned
                    if outcome is not None and outcome[1].error_code in LIMIT_CODES
                }
                if limit_codes:
                    code = sorted(limit_codes)[0]
                    detail = "A turn limit was reached."
                    if approval_specs:
                        for index, call, _arguments in approval_specs:
                            planned[index] = (
                                call,
                                _limit_outcome(call.name, code, detail),
                            )
                    outcomes = _planned_outcomes(calls, planned)
                    try:
                        result_entries = await self.repository.append_tool_results(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            drafts=[
                                _tool_result_draft(call, outcome) for call, outcome in outcomes
                            ],
                            now=utcnow(),
                        )
                    except AgentRunNotActiveError:
                        await self._best_effort_cancel(turn, last_entry_id)
                        terminal = True
                        yield AgentStreamEvent(
                            "run_end",
                            {"run_id": run_id, "status": RUN_CANCELLED},
                        )
                        return
                    last_entry_id = result_entries[-1].id if result_entries else last_entry_id
                    for index, ((call, outcome), entry) in enumerate(
                        zip(outcomes, result_entries, strict=True)
                    ):
                        yield _tool_end_event(
                            call,
                            outcome,
                            entry.id,
                            parallel=parallel,
                            batch_size=batch_size,
                            parallel_index=index,
                        )
                    await self._fail_run(turn, last_entry_id, code, detail)
                    terminal = True
                    yield AgentStreamEvent("error", {"code": code, "detail": detail})
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                if approval_specs:
                    # Batch rule: every non-confirmation call runs normally;
                    # each valid confirmation call becomes a pending approval
                    # in assistant call order. No result is invented for a
                    # pending call. Resolutions must follow approval id order,
                    # so tool results still append in source order.
                    result_indices = [
                        index for index, value in enumerate(planned) if value is not None
                    ]
                    result_drafts: list[EntryDraft] = []
                    result_pairs: list[tuple[ChatToolCall, ToolOutcome]] = []
                    for index in result_indices:
                        planned_outcome = planned[index]
                        assert planned_outcome is not None
                        result_pairs.append(planned_outcome)
                        result_drafts.append(_tool_result_draft(*planned_outcome))
                    approval_drafts = [
                        ApprovalDraft(
                            tool_call_id=call.call_id,
                            tool_name=call.name,
                            arguments=arguments,
                            preview=_approval_preview(call.name, arguments),
                            resume_state={
                                "step": step,
                                "total_usage": dict(total_usage),
                                "tool_calls_used": tool_calls_used,
                                "assistant_entry_id": assistant_entry.id,
                                "batch_size": batch_size,
                                "parallel": parallel,
                                "parallel_index": index,
                            },
                        )
                        for index, call, arguments in approval_specs
                    ]
                    try:
                        result_entries, approvals = await self.repository.pause_run_with_approvals(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            result_drafts=result_drafts,
                            approval_drafts=approval_drafts,
                            last_entry_id=last_entry_id,
                            now=utcnow(),
                        )
                    except AgentRunNotActiveError:
                        await self._best_effort_cancel(turn, last_entry_id)
                        terminal = True
                        yield AgentStreamEvent(
                            "run_end",
                            {"run_id": run_id, "status": RUN_CANCELLED},
                        )
                        return
                    if result_entries:
                        last_entry_id = result_entries[-1].id
                    for index, (call, outcome), entry in zip(
                        result_indices,
                        result_pairs,
                        result_entries,
                        strict=True,
                    ):
                        yield _tool_end_event(
                            call,
                            outcome,
                            entry.id,
                            parallel=parallel,
                            batch_size=batch_size,
                            parallel_index=index,
                        )
                    for approval in approvals:
                        yield _approval_required_event(_approval_schema(approval))
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_WAITING},
                    )
                    return

                # Each executed outcome was already clipped to the per-result
                # cap by the tool registry. Calls over the per-turn call limit
                # carry a small synthetic limit outcome; no result is dropped
                # or summarized with a second model call.
                outcomes = _planned_outcomes(calls, planned)

                try:
                    result_entries = await self.repository.append_tool_results(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        drafts=[_tool_result_draft(call, outcome) for call, outcome in outcomes],
                        now=utcnow(),
                    )
                except AgentRunNotActiveError:
                    await self._best_effort_cancel(turn, last_entry_id)
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return
                last_entry_id = result_entries[-1].id if result_entries else last_entry_id
                for index, ((call, outcome), entry) in enumerate(
                    zip(outcomes, result_entries, strict=True)
                ):
                    yield _tool_end_event(
                        call,
                        outcome,
                        entry.id,
                        parallel=parallel,
                        batch_size=batch_size,
                        parallel_index=index,
                    )

                context = await self._context(conversation_id, last_entry_id)

            last_entry_id = await self._append_failure_assistant(
                turn,
                last_entry_id,
                "step_limit",
                "The step limit was reached.",
                self.config.max_steps + 1,
            )
            await self._fail_run(
                turn,
                last_entry_id,
                "step_limit",
                "The step limit was reached.",
            )
            terminal = True
            yield AgentStreamEvent(
                "error",
                {"code": "step_limit", "detail": "The step limit was reached."},
            )
            yield AgentStreamEvent(
                "run_end",
                {"run_id": run_id, "status": RUN_FAILED},
            )
        except asyncio.CancelledError:
            await self._best_effort_cancel(turn, last_entry_id)
            terminal = True
            raise
        except Exception:
            logger.exception("Agent run %s failed", run_id)
            await self._best_effort_fail(
                turn,
                last_entry_id,
                "internal_error",
                "The agent run failed.",
            )
            terminal = True
            yield AgentStreamEvent(
                "error",
                {"code": "internal_error", "detail": "The agent run failed."},
            )
            yield AgentStreamEvent(
                "run_end",
                {"run_id": run_id, "status": RUN_FAILED},
            )
        finally:
            if not terminal:
                await self._best_effort_cancel(turn, last_entry_id)

    async def collect_turn(self, turn: AgentTurnState) -> AgentTurnResultSchema:
        """Consume a turn and return its completed durable state as JSON."""
        async for _event in self.stream_turn(turn):
            pass
        run = await self.repository.get_run(turn.run.id)
        if run is None:
            raise AgentRunNotFoundError(turn.run.id)
        rows = await self.repository.list_run_entries(run.id)
        entries = [_entry_schema(row) for row in rows]
        if not any(entry.id == turn.user_entry.id for entry in entries):
            entries.insert(0, turn.user_entry)
        assistant_entries = [entry for entry in entries if entry.kind == KIND_ASSISTANT]
        tool_results = [entry for entry in entries if entry.kind == KIND_TOOL_RESULT]
        pending = await self.repository.list_pending_approvals(run.id)
        return AgentTurnResultSchema(
            run=_run_schema(run),
            user_entry=turn.user_entry,
            entries=entries,
            assistant_entry=assistant_entries[-1] if assistant_entries else None,
            tool_results=tool_results,
            answer=_answer_text(assistant_entries),
            usage=_usage_from_entries(entries),
            error_code=run.error_code,
            error_detail=run.error_detail,
            pending_approvals=[_approval_schema(item) for item in pending],
        )

    async def list_approvals(
        self,
        conversation_id: int,
        *,
        status: str | None,
    ) -> list[AgentApprovalSchema]:
        """Return durable approvals for one conversation, oldest first."""
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        rows = await self.repository.list_approvals(
            conversation_id,
            status=status,
        )
        return [_approval_schema(row) for row in rows]

    async def resolve_approval(
        self,
        approval_id: int,
        *,
        approved: bool,
    ) -> AgentApprovalTurn:
        """Resolve exactly one pending approval and prepare its resumed loop.

        The approval row is claimed before the write executes, so a duplicate or
        concurrent resolution can never double-write. A rejected write appends a
        clear error tool result and resumes without touching memory.
        """
        approval = await self.repository.get_approval(approval_id)
        if approval is None:
            raise AgentApprovalNotFoundError(approval_id)
        conversation_row = await self.repository.get_conversation(approval.conversation_id)
        if conversation_row is None:
            raise AgentConversationNotFoundError(approval.conversation_id)
        if conversation_row.status != "active":
            raise AgentConversationArchivedError(approval.conversation_id)

        claimed, run, conversation = await self.repository.claim_approval(
            approval_id=approval_id,
            approved=approved,
            now=utcnow(),
        )
        call = ChatToolCall(
            call_id=claimed.tool_call_id,
            name=claimed.tool_name,
            arguments=claimed.arguments,
            raw_arguments=json.dumps(
                claimed.arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if approved:
            outcome = await self.tool_registry.execute(
                call.name,
                call.arguments,
                call_id=call.call_id,
                max_chars=self.config.max_tool_result_chars,
                approved=True,
            )
        else:
            outcome = _rejection_outcome(call.name, approval_id)

        tool_entry, run, conversation, remaining = await self.repository.record_approval_result(
            approval_id=approval_id,
            draft=_tool_result_draft(call, outcome),
            now=utcnow(),
        )
        user_entry = await self.repository.get_entry(run.user_entry_id)
        if user_entry is None:
            raise AgentRunNotFoundError(run.id)
        latest = await self.repository.get_approval(approval_id)
        if latest is None:
            raise AgentApprovalNotFoundError(approval_id)

        resume_state = dict(claimed.resume_state)
        return AgentApprovalTurn(
            turn=AgentTurnState(
                conversation=_conversation_schema(conversation),
                run=_run_schema(run),
                user_entry=_entry_schema(user_entry),
                cutoff_entry_id=run.last_entry_id or tool_entry.id,
                page_context_entry_id=None,
            ),
            approval=_approval_schema(latest),
            call=call,
            outcome=outcome,
            tool_entry=_entry_schema(tool_entry),
            remaining=[_approval_schema(item) for item in remaining],
            resume_state=resume_state,
        )

    async def stream_approval(
        self,
        approval_turn: AgentApprovalTurn,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Stream the resolution and, when no approvals remain, the resume."""
        run_id = approval_turn.turn.run.id
        yield AgentStreamEvent(
            "run_start",
            {
                "run_id": run_id,
                "user_entry_id": approval_turn.turn.user_entry.id,
                "page_context_entry_id": None,
                "page_context_attached": False,
                "resumed": True,
            },
        )
        yield _tool_end_event(
            approval_turn.call,
            approval_turn.outcome,
            approval_turn.tool_entry.id,
        )
        if approval_turn.remaining:
            for approval in approval_turn.remaining:
                yield _approval_required_event(approval)
            yield AgentStreamEvent(
                "run_end",
                {"run_id": run_id, "status": RUN_WAITING},
            )
            return

        start_step = int(approval_turn.resume_state.get("step", 0)) + 1
        usage = approval_turn.resume_state.get("total_usage")
        total_usage = (
            {str(key): int(value) for key, value in usage.items()}
            if isinstance(usage, dict)
            else {}
        )
        tool_calls_used = int(approval_turn.resume_state.get("tool_calls_used", 0))
        async for event in self._run_loop(
            approval_turn.turn,
            start_step=start_step,
            total_usage=total_usage,
            tool_calls_used=tool_calls_used,
            last_entry_id=approval_turn.turn.cutoff_entry_id,
            resumed=True,
            emit_start=False,
        ):
            yield event

    async def collect_approval(
        self,
        approval_turn: AgentApprovalTurn,
    ) -> AgentTurnResultSchema:
        """Consume an approval resolution and return the final durable turn."""
        async for _event in self.stream_approval(approval_turn):
            pass
        return await self.collect_turn(approval_turn.turn)

    async def _execute_tool(
        self,
        call: ChatToolCall,
        *,
        approved: bool = False,
    ) -> ToolOutcome:
        """Execute one call with the snapshot's per-result character cap.

        ``approved`` is true only when the backend itself authorized a
        confirmation-required write for this snapshot; it never comes from the
        model's tool arguments.
        """
        return await self.tool_registry.execute(
            call.name,
            call.arguments,
            call_id=call.call_id,
            max_chars=self.config.max_tool_result_chars,
            parse_error=call.parse_error,
            approved=approved,
        )

    async def _gather_tools(
        self,
        calls: list[ChatToolCall],
        indices: list[int],
        approved_indices: set[int],
    ) -> list[ToolOutcome]:
        """Run eligible calls concurrently, bounded by max_parallel_tools.

        ``asyncio.gather`` returns results in input order, so the persisted tool
        results (and their tool_end events) stay deterministic.
        """
        semaphore = asyncio.Semaphore(self.config.max_parallel_tools)

        async def run(index: int) -> ToolOutcome:
            async with semaphore:
                return await self._execute_tool(
                    calls[index],
                    approved=index in approved_indices,
                )

        return list(await asyncio.gather(*(run(index) for index in indices)))

    async def _completion_events(
        self,
        context: ProviderContext,
        model: str,
        outcome: _CompletionOutcome,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Run one provider call and yield transport-only text deltas."""
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def on_delta(delta: str) -> None:
            await queue.put(("delta", delta))

        async def run() -> None:
            try:
                provider_messages: list[dict[str, Any]] = []
                if context.system_message.get("content"):
                    provider_messages.append(context.system_message)
                provider_messages.extend(context.messages)
                result = await self.chat_generator.complete_chat(
                    provider_messages,
                    context.tools,
                    model=model,
                    stream=True,
                    on_text_delta=on_delta,
                )
                await queue.put(("result", result))
            except Exception as exc:
                await queue.put(("error", exc))

        task = asyncio.create_task(run())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "delta":
                    yield AgentStreamEvent(
                        "message_delta",
                        {"entry_id": None, "delta": payload},
                    )
                    continue
                if kind == "result":
                    outcome.result = payload if isinstance(payload, ChatResult) else None
                    if outcome.result is None:
                        outcome.error = RuntimeError("provider returned an invalid result")
                    return
                outcome.error = (
                    payload if isinstance(payload, Exception) else RuntimeError("provider")
                )
                return
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _context(
        self,
        conversation_id: int,
        cutoff_entry_id: int | None,
    ) -> ProviderContext:
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=cutoff_entry_id,
        )
        return build_context(_transcript_from_rows(rows))

    async def _append_failure_assistant(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        code: str,
        detail: str,
        step: int,
    ) -> int:
        draft = EntryDraft(
            kind=KIND_ASSISTANT,
            messages=[{"role": "assistant", "content": ""}],
            data={
                "finish_reason": "error",
                "error": {"code": code, "detail": detail},
                "model": turn.conversation.model,
                "provider": turn.conversation.provider,
                "step": step,
            },
        )
        try:
            entry = await self.repository.append_assistant(
                conversation_id=turn.conversation.id,
                run_id=turn.run.id,
                draft=draft,
                now=utcnow(),
            )
        except AgentRunNotActiveError:
            return last_entry_id
        return entry.id

    async def _append_provider_failure(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        error: Exception | None,
        step: int,
    ) -> tuple[int, str, str]:
        if isinstance(error, AiNotConfiguredError):
            code = "not_configured"
            detail = "No chat provider is configured."
        else:
            code = "provider_error"
            detail = "The chat provider failed."
        logger.warning(
            "Agent provider failure for run %s: %s",
            turn.run.id,
            type(error).__name__ if error is not None else "unknown",
        )
        entry_id = await self._append_failure_assistant(
            turn,
            last_entry_id,
            code,
            detail,
            step,
        )
        return entry_id, code, detail

    async def _limit_tool_batch(
        self,
        turn: AgentTurnState,
        calls: list[ChatToolCall],
        code: str,
        detail: str,
    ) -> tuple[list[AgentEntryModel] | None, list[AgentStreamEvent]]:
        """Persist error results for calls that could not run due to a cap."""
        events = [
            AgentStreamEvent(
                "tool_start",
                {
                    "entry_id": None,
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                },
            )
            for call in calls
        ]
        outcomes = [_limit_outcome(call.name, code, detail) for call in calls]
        try:
            entries = await self.repository.append_tool_results(
                conversation_id=turn.conversation.id,
                run_id=turn.run.id,
                drafts=[
                    _tool_result_draft(call, outcome)
                    for call, outcome in zip(calls, outcomes, strict=True)
                ],
                now=utcnow(),
            )
        except AgentRunNotActiveError:
            return None, events
        events.extend(
            _tool_end_event(
                call,
                outcome,
                entry.id,
                parallel=len(calls) > 1,
                batch_size=len(calls),
                parallel_index=index,
            )
            for index, (call, outcome, entry) in enumerate(
                zip(calls, outcomes, entries, strict=True)
            )
        )
        return entries, events

    async def _fail_run(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        code: str,
        detail: str,
    ) -> None:
        await self.repository.fail_run(
            conversation_id=turn.conversation.id,
            run_id=turn.run.id,
            error_code=code,
            error_detail=detail,
            last_entry_id=last_entry_id,
            now=utcnow(),
        )

    async def _best_effort_fail(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        code: str,
        detail: str,
    ) -> None:
        try:
            await self._fail_run(turn, last_entry_id, code, detail)
        except Exception:
            logger.exception("Could not mark agent run %s as failed", turn.run.id)

    async def _best_effort_cancel(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
    ) -> None:
        task = asyncio.create_task(
            self.repository.cancel_run(
                conversation_id=turn.conversation.id,
                run_id=turn.run.id,
                last_entry_id=last_entry_id,
                now=utcnow(),
            )
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            logger.info("Agent run %s cancellation is settling in the background", turn.run.id)
        except Exception:
            logger.exception("Could not mark agent run %s as cancelled", turn.run.id)

    def _ensure_configured(self) -> None:
        if not self.chat_generator.configured:
            raise AgentNotConfiguredError()


def _transcript_from_rows(rows: list[AgentEntryModel]) -> list[TranscriptEntry]:
    transcript: list[TranscriptEntry] = []
    for row in rows:
        try:
            edits = parse_edits(row.edits)
        except ValueError as exc:
            raise AgentInvalidEntryError(str(exc)) from exc
        transcript.append(
            TranscriptEntry(
                id=row.id,
                kind=row.kind,
                messages=tuple(row.model or []),
                data=row.data,
                head_entry_id=row.head_entry_id,
                edits=edits,
                by_run_id=row.by_run_id,
            )
        )
    return transcript


def _page_context_draft(
    context: AgentPageContextSchema | None,
    *,
    max_chars: int,
) -> tuple[EntryDraft | None, str | None]:
    """Build the UI payload and provider message for one page snapshot.

    Page context is append-only data. It is sent as a user-role message so the
    model sees it next to the question, but the visible user entry always keeps
    exactly the user's own text. ``max_chars`` comes from the runtime snapshot.
    """
    if context is None:
        return None, None
    key = context.key.strip()
    path = context.path.strip()
    title: str | None = (" ".join(context.title.split()) if context.title else "") or None
    text = _normalize_page_text(context.text)
    if not key or not path or not text:
        return None, None

    truncated = len(text) > max_chars
    if truncated:
        text = clip(text, max_chars)
    values: dict[str, object] = {"key": key, "path": path}
    if title:
        values["title"] = title
    provider_content = (
        f"<page_context{attributes(values)}><text>{xml_text(text)}</text></page_context>"
    )
    data = {
        "page_key": key,
        "path": path,
        "title": title,
        "text_chars": len(text),
        "truncated": truncated,
    }
    return (
        EntryDraft(
            kind=KIND_PAGE_CONTEXT,
            messages=[{"role": "user", "content": provider_content}],
            data=data,
        ),
        key,
    )


def _normalize_page_text(value: str) -> str:
    """Normalize line endings and whitespace without losing paragraph breaks."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [_PAGE_CONTEXT_LINE_WS.sub(" ", line).strip() for line in normalized.split("\n")]
    normalized = "\n".join(lines).strip()
    return _PAGE_CONTEXT_BLANK_LINES.sub("\n\n", normalized)


def _conversation_schema(model: AgentConversationModel) -> AgentConversationSchema:
    return AgentConversationSchema.model_validate(model)


def _entry_schema(model: AgentEntryModel) -> AgentEntrySchema:
    return AgentEntrySchema.model_validate(model)


def _run_schema(model: AgentRunModel) -> AgentRunSchema:
    return AgentRunSchema.model_validate(model)


def _entry_page(
    conversation_id: int,
    rows: list[AgentEntryModel],
    total: int,
    has_more: bool,
) -> AgentEntryPageSchema:
    entries = [_entry_schema(row) for row in rows]
    return AgentEntryPageSchema(
        conversation_id=conversation_id,
        total_results=total,
        entries=entries,
        next_after_id=entries[-1].id if has_more and entries else None,
        has_more=has_more,
    )


def _assistant_message(result: ChatResult) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": result.text,
    }
    if result.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": _arguments_json(call),
                },
            }
            for call in result.tool_calls
        ]
    return message


def _arguments_json(call: ChatToolCall) -> str:
    if call.parse_error is not None and call.raw_arguments:
        return call.raw_arguments
    return json.dumps(
        call.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _assistant_data(
    result: ChatResult,
    turn: AgentTurnState,
    step: int,
    finish_reason: str,
    cache_prefix_hash: str,
) -> dict[str, Any]:
    return {
        "finish_reason": finish_reason,
        "usage": dict(result.usage),
        "model": result.model or turn.conversation.model,
        "provider": turn.conversation.provider,
        "step": step,
        "cache_prefix_hash": cache_prefix_hash,
        "citations": list(dict.fromkeys(CITATION_PATTERN.findall(result.text))),
    }


def _normalize_finish(result: ChatResult) -> str | None:
    finish = (result.finish_reason or "").lower()
    if result.tool_calls:
        if finish in {"length", "content_filter"} or finish in ERROR_FINISH_REASONS:
            return None
        return "tool_calls"
    if not result.text.strip():
        return None
    if finish in {"", "stop", "length"}:
        return finish or "stop"
    return None


def _planned_outcomes(
    calls: list[ChatToolCall],
    planned: list[tuple[ChatToolCall, ToolOutcome] | None],
) -> list[tuple[ChatToolCall, ToolOutcome]]:
    """Return every call with a concrete outcome, preserving source order."""
    outcomes: list[tuple[ChatToolCall, ToolOutcome]] = []
    for index, _call in enumerate(calls):
        planned_outcome = planned[index]
        assert planned_outcome is not None
        outcomes.append(planned_outcome)
    return outcomes


def _approval_preview(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Build a bounded, human-readable preview for the approval card."""
    raw_content = arguments.get("content")
    content = raw_content if isinstance(raw_content, str) else ""
    raw_supersedes = arguments.get("supersedes")
    supersedes = (
        [value for value in raw_supersedes if isinstance(value, int)]
        if isinstance(raw_supersedes, list)
        else []
    )
    raw_occurred_at = arguments.get("occurred_at")
    raw_reason = arguments.get("reason")
    reason = raw_reason if isinstance(raw_reason, str) else None
    mode = "deprecate" if not content.strip() and supersedes else "save"
    return {
        "tool": tool_name,
        "mode": mode,
        "content": content,
        "content_chars": len(content),
        "supersedes": supersedes,
        "reason": reason,
        "occurred_at": (raw_occurred_at if isinstance(raw_occurred_at, str) else None),
        "risk": (
            "Approving marks the listed memories deprecated and removes them "
            "from default retrieval. Their rows and text remain readable. "
            "Rejecting changes nothing."
            if mode == "deprecate"
            else "Approving appends a durable memory to the archive. Rejecting "
            "writes nothing and tells the agent the write was declined."
        ),
    }


def _approval_schema(model: AgentApprovalModel) -> AgentApprovalSchema:
    return AgentApprovalSchema.model_validate(model)


def _approval_required_event(approval: AgentApprovalSchema) -> AgentStreamEvent:
    return AgentStreamEvent(
        "approval_required",
        {
            "approval_id": approval.id,
            "conversation_id": approval.conversation_id,
            "run_id": approval.run_id,
            "tool_call_id": approval.tool_call_id,
            "tool_name": approval.tool_name,
            "status": approval.status,
            "preview": approval.preview,
            "requested_at": approval.requested_at.isoformat(),
        },
    )


def _rejection_outcome(tool_name: str, approval_id: int) -> ToolOutcome:
    detail = "The user rejected the proposed memory action. No memory was saved or deprecated."
    return ToolOutcome(
        content=f"<error{attributes({'code': 'memory_rejected'})}>{xml_text(detail)}</error>",
        data={
            "tool": tool_name,
            "status": "error",
            "error_code": "memory_rejected",
            "detail": detail,
            "approval_id": approval_id,
        },
        status="error",
        error_code="memory_rejected",
    )


def _tool_result_draft(call: ChatToolCall, outcome: ToolOutcome) -> EntryDraft:
    return EntryDraft(
        kind=KIND_TOOL_RESULT,
        messages=[
            {
                "role": "tool",
                "tool_call_id": call.call_id,
                "name": call.name,
                "content": render_tool_result(
                    call.call_id,
                    call.name,
                    outcome.content,
                ),
            }
        ],
        data={
            **outcome.data,
            "tool": call.name,
            "status": outcome.status,
            "error_code": outcome.error_code,
            "duration_ms": outcome.data.get("duration_ms"),
            "arguments": call.arguments,
            "resource": outcome.resource,
        },
    )


def _tool_end_event(
    call: ChatToolCall,
    outcome: ToolOutcome,
    entry_id: int,
    *,
    parallel: bool = False,
    batch_size: int = 1,
    parallel_index: int = 0,
) -> AgentStreamEvent:
    data: dict[str, Any] = {
        "entry_id": entry_id,
        "tool_call_id": call.call_id,
        "name": call.name,
        "status": outcome.status,
        "error_code": outcome.error_code,
        "duration_ms": outcome.data.get("duration_ms"),
        "data": outcome.data,
        "parallel": parallel,
        "batch_size": batch_size,
        "parallel_index": parallel_index,
    }
    if outcome.resource is not None:
        data["resource"] = outcome.resource
    return AgentStreamEvent("tool_end", data)


def _limit_outcome(name: str, code: str, detail: str) -> ToolOutcome:
    return ToolOutcome(
        content=f"<error{attributes({'code': code})}>{xml_text(detail)}</error>",
        data={
            "tool": name,
            "status": "error",
            "error_code": code,
            "detail": detail,
        },
        status="error",
        error_code=code,
    )


def _merge_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value


def _token_total(usage: dict[str, int]) -> int:
    if "total_tokens" in usage:
        return int(usage["total_tokens"])
    return int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))


def _usage_from_entries(entries: list[AgentEntrySchema]) -> dict[str, int]:
    total: dict[str, int] = {}
    for entry in entries:
        if entry.kind != KIND_ASSISTANT or not isinstance(entry.data, dict):
            continue
        usage = entry.data.get("usage")
        if isinstance(usage, dict):
            _merge_usage(
                total,
                {str(key): int(value) for key, value in usage.items() if isinstance(value, int)},
            )
    return total


def _answer_text(assistant_entries: list[AgentEntrySchema]) -> str | None:
    for entry in reversed(assistant_entries):
        for message in reversed(entry.model or []):
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None
