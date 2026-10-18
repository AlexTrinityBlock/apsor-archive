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

from app.module.agent.domain.agent_domain import (
    ERROR_FINISH_REASONS,
    KIND_ASSISTANT,
    KIND_TOOL_RESULT,
    KIND_USER,
    MAX_STEPS,
    MAX_TOOL_CALLS_PER_TURN,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOTAL_TOKENS,
    MAX_TOTAL_TOOL_RESULT_CHARS,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    AgentStreamEvent,
    EntryDraft,
    ProviderContext,
    ToolOutcome,
    TranscriptEntry,
    parse_edits,
)
from app.module.agent.domain.context_domain import build_context, render_tool_result
from app.module.agent.domain.tool_catalog import PROMPT_VERSION, TOOLS_VERSION
from app.module.agent.domain.xml_domain import attributes, xml_text
from app.module.agent.exception.domain_error import (
    AgentConversationArchivedError,
    AgentConversationNotFoundError,
    AgentInvalidEntryError,
    AgentNotConfiguredError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
    AgentRunNotRetryableError,
)
from app.module.agent.model.agent_model import (
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
    AgentConversationCreateSchema,
    AgentConversationDetailSchema,
    AgentConversationPatchSchema,
    AgentConversationSchema,
    AgentEntryPageSchema,
    AgentEntrySchema,
    AgentMessageCreateSchema,
    AgentRetrySchema,
    AgentRunSchema,
    AgentToolCatalogSchema,
    AgentToolSchema,
    AgentTurnResultSchema,
)
from app.module.agent.service.system_prompt import build_system_data, build_system_model
from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.knowledge.exception.domain_error import AiNotConfiguredError
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"\[(?:file|memory|media|summary):\d+(?:#\d+)?\]")
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


@dataclass
class _CompletionOutcome:
    """Mutable holder for an async-generator completion."""

    result: ChatResult | None = None
    error: Exception | None = None


class AgentService:
    """Own conversation CRUD and the durable multi-step turn loop."""

    def __init__(
        self,
        *,
        repository: AgentRepositoryProtocol,
        chat_generator: ChatGeneratorProtocol,
        tool_registry: AgentToolRegistry,
        default_provider: str,
        default_model: str,
    ) -> None:
        self.repository = repository
        self.chat_generator = chat_generator
        self.tool_registry = tool_registry
        self.default_provider = default_provider
        self.default_model = default_model

    async def create_conversation(
        self,
        payload: AgentConversationCreateSchema,
    ) -> AgentConversationSchema:
        provider = payload.provider or self.default_provider
        if provider not in {"deepseek", "openai-compatible"}:
            provider = "deepseek"
        model = payload.model or self.default_model or "deepseek-flash"
        now = utcnow()
        system_data = build_system_data(provider=provider, model=model)
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
        return AgentConversationDetailSchema(
            **base.model_dump(),
            entries=page.entries,
            entries_total=page.total_results,
            entries_next_after_id=page.next_after_id,
            entries_has_more=page.has_more,
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
        data: dict[str, Any] | None = None
        if payload.request_id is not None:
            data = {"request_id": payload.request_id}
        conversation_model, user_entry, run = await self.repository.append_user_and_run(
            conversation_id=conversation_id,
            draft=EntryDraft(
                kind=KIND_USER,
                messages=[{"role": "user", "content": content}],
                data=data,
            ),
            request_id=payload.request_id,
            now=utcnow(),
        )
        return AgentTurnState(
            conversation=_conversation_schema(conversation_model),
            run=_run_schema(run),
            user_entry=_entry_schema(user_entry),
            cutoff_entry_id=user_entry.id,
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
        )

    async def stream_turn(self, turn: AgentTurnState) -> AsyncIterator[AgentStreamEvent]:
        """Run the model/tool loop and yield transport-only events."""
        conversation_id = turn.conversation.id
        run_id = turn.run.id
        last_entry_id = turn.cutoff_entry_id
        terminal = False
        total_usage: dict[str, int] = {}
        tool_calls_used = 0
        tool_result_chars = 0

        try:
            yield AgentStreamEvent(
                "run_start",
                {"run_id": run_id, "user_entry_id": turn.user_entry.id},
            )
            context = await self._context(conversation_id, turn.cutoff_entry_id)

            for step in range(1, MAX_STEPS + 1):
                if await self.repository.is_abort_requested(conversation_id, run_id):
                    await self._best_effort_cancel(turn, last_entry_id)
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return

                if _token_total(total_usage) >= MAX_TOTAL_TOKENS:
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
                if step >= MAX_STEPS:
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
                    last_entry_id = (
                        limit_entries[-1].id if limit_entries else last_entry_id
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
                    return

                if _token_total(total_usage) >= MAX_TOTAL_TOKENS:
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
                    last_entry_id = (
                        limit_entries[-1].id if limit_entries else last_entry_id
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

                outcomes: list[tuple[ChatToolCall, ToolOutcome]] = []
                for call in calls:
                    yield AgentStreamEvent(
                        "tool_start",
                        {
                            "entry_id": None,
                            "tool_call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    )
                    remaining_chars = MAX_TOTAL_TOOL_RESULT_CHARS - tool_result_chars
                    if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                        outcome = _limit_outcome(
                            call.name,
                            "tool_call_limit",
                            "The tool-call limit was reached for this turn.",
                        )
                    elif remaining_chars <= 0:
                        outcome = _limit_outcome(
                            call.name,
                            "tool_result_budget_exhausted",
                            "The tool-result budget was exhausted for this turn.",
                        )
                    else:
                        outcome = await self.tool_registry.execute(
                            call.name,
                            call.arguments,
                            call_id=call.call_id,
                            max_chars=min(MAX_TOOL_RESULT_CHARS, remaining_chars),
                            parse_error=call.parse_error,
                        )
                        tool_calls_used += 1
                        tool_result_chars += len(outcome.content)
                    outcomes.append((call, outcome))

                try:
                    result_entries = await self.repository.append_tool_results(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        drafts=[
                            _tool_result_draft(call, outcome)
                            for call, outcome in outcomes
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
                last_entry_id = (
                    result_entries[-1].id if result_entries else last_entry_id
                )
                for (call, outcome), entry in zip(
                    outcomes,
                    result_entries,
                    strict=True,
                ):
                    yield _tool_end_event(call, outcome, entry.id)

                limit_codes = {
                    outcome.error_code
                    for _call, outcome in outcomes
                    if outcome.error_code in LIMIT_CODES
                }
                if limit_codes:
                    code = sorted(limit_codes)[0]
                    detail = "A turn limit was reached."
                    await self._fail_run(turn, last_entry_id, code, detail)
                    terminal = True
                    yield AgentStreamEvent("error", {"code": code, "detail": detail})
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                context = await self._context(conversation_id, last_entry_id)

            last_entry_id = await self._append_failure_assistant(
                turn,
                last_entry_id,
                "step_limit",
                "The step limit was reached.",
                MAX_STEPS + 1,
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
        assistant_entries = [
            entry for entry in entries if entry.kind == KIND_ASSISTANT
        ]
        tool_results = [
            entry for entry in entries if entry.kind == KIND_TOOL_RESULT
        ]
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
        )

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
                    outcome.result = (
                        payload if isinstance(payload, ChatResult) else None
                    )
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
        return build_context(transcript)

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
            _tool_end_event(call, outcome, entry.id)
            for call, outcome, entry in zip(calls, outcomes, entries, strict=True)
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
) -> AgentStreamEvent:
    data: dict[str, Any] = {
        "entry_id": entry_id,
        "tool_call_id": call.call_id,
        "name": call.name,
        "status": outcome.status,
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
                {
                    str(key): int(value)
                    for key, value in usage.items()
                    if isinstance(value, int)
                },
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
