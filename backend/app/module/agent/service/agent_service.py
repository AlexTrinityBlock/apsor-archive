"""Conversation orchestration, the Pi-shaped tool loop, and SSE turn events."""

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import uuid4

from app.infrastructure.ai.model_catalog import chars_per_token_for
from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.domain.agent_domain import (
    ERROR_FINISH_REASONS,
    KIND_ASSISTANT,
    KIND_COMPACTION,
    KIND_NOTICE,
    KIND_PAGE_CONTEXT,
    KIND_RESET,
    KIND_SYSTEM,
    KIND_TOOL_RESULT,
    KIND_USER,
    MAX_ASSISTANT_REASONING_CHARS,
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
from app.module.agent.domain.agent_status_domain import (
    AgentStatus,
    render_agent_status,
    render_context_overflow_notice,
    render_invalid_arguments_notice,
    render_output_limit_notice,
)
from app.module.agent.domain.compaction_domain import (
    active_context_entries,
    build_compaction_draft,
    compactable_context_entries,
    estimate_context_tokens,
    estimate_provider_context_tokens,
    render_compaction_prompt,
)
from app.module.agent.domain.context_domain import build_context, render_tool_result
from app.module.agent.domain.plot_spec_domain import PlotLimits
from app.module.agent.domain.tool_args import MAX_EXPRESSION_CHARS
from app.module.agent.domain.tool_catalog import (
    PROMPT_VERSION,
    TOOLS_VERSION,
    display_arguments,
)
from app.module.agent.domain.user_profile_domain import UserProfile
from app.module.agent.domain.xml_domain import attributes, clip, xml_text
from app.module.agent.exception.domain_error import (
    AgentApprovalNotFoundError,
    AgentConversationArchivedError,
    AgentConversationNotFoundError,
    AgentInvalidEntryError,
    AgentNotConfiguredError,
    AgentOutputLimitError,
    AgentRunNotActiveError,
    AgentRunNotFoundError,
    AgentRunNotRetryableError,
    AgentUsageLimitExceededError,
    ModelNotAssignedError,
    ProviderInactiveError,
)
from app.module.agent.model.agent_model import (
    AgentApprovalModel,
    AgentConversationModel,
    AgentEntryModel,
    AgentRunModel,
)
from app.module.agent.protocol.agent_repository_protocol import AgentRepositoryProtocol
from app.module.agent.protocol.chat_attachment_service_protocol import (
    ChatAttachmentServiceProtocol,
)
from app.module.agent.protocol.chat_generator_protocol import (
    ChatGeneratorProtocol,
    ChatResult,
    ChatToolCall,
)
from app.module.agent.protocol.usage_quota_protocol import AgentQuotaProtocol
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
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiNotConfiguredError,
    AiProviderError,
)
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(
    r"\[(?:(?:file|memory|summary):\d+(?:#\d+)?|history:\d+)\]"
)
_PAGE_CONTEXT_LINE_WS = re.compile(r"[ \t\f\v]+")
_PAGE_CONTEXT_BLANK_LINES = re.compile(r"\n{3,}")
LIMIT_CODES = frozenset(
    {"step_limit", "tool_call_limit", "tool_result_budget_exhausted"}
)
DUPLICATE_PLOT_STOP_TEXT = (
    "The chart is already visible in the chat, so I did not render another copy. "
    "If you want a different chart, describe it in your next message."
)
# A transient upstream outage is retried only when no text has reached the
# client yet. Delays are deliberately short: the durable run is still
# retryable from the UI after these automatic attempts are exhausted.
_PROVIDER_RETRY_DELAYS_SECONDS = (1.0, 3.0)
# Two rejected tool calls in a row get an actionable retry notice; a third one
# switches the next provider call to text-only so the run cannot burn its whole
# step budget on the same invalid arguments. Any other tool outcome resets the
# streak.
_INVALID_ARGUMENT_ERROR_CODES = frozenset({"invalid_tool_arguments"})
_INVALID_ARGUMENTS_NOTICE_THRESHOLD = 2
_INVALID_ARGUMENTS_TEXT_ONLY_THRESHOLD = 3
# The local context-budget ladder. Each tool-result pass clips a body to the
# next cap and re-estimates; the current user message is only touched after
# page context is gone and tool results are as small as this ladder allows.
_TOOL_RESULT_BODY_CAPS = (8_000, 2_000, 500)
_FORCED_COMPACTION_BUDGET_RATIO = 0.6
_USER_MESSAGE_HEAD_RATIO = 0.6
_IMAGE_OMITTED_TEXT = "[image omitted: context budget]"
_ATTACHMENT_PART_TYPES = frozenset({"image", "image_url", "document", "input_file"})
# ``context_used`` renders its own estimate, so the trailing status block needs
# a bounded fixed-point pass. The digits settle after at most one change.
_AGENT_STATUS_ESTIMATE_ATTEMPTS = 3


class AgentModelPlanProtocol(Protocol):
    """One primary endpoint plus its optional single escalation target."""

    def next_model(self, current_model: str) -> str | None: ...

    def generator_for(self, model: str) -> ChatGeneratorProtocol: ...


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
    """Mutable holder for an async-generator completion.

    ``text`` keeps every delta already sent to the client so a provider timeout
    can persist the visible prefix instead of losing it behind an empty error
    entry.
    """

    result: ChatResult | None = None
    error: Exception | None = None
    text: str = ""
    # Provider-reported reasoning streamed before the visible answer. It is
    # transport/UI telemetry and never part of the provider messages.
    reasoning: str = ""


@dataclass
class _BudgetStats:
    """What the local overflow ladder removed from one outbound request."""

    dropped_messages: int = 0
    dropped_page_contexts: int = 0
    clipped_tool_results: int = 0
    truncated_user_chars: int = 0
    truncated_attachments: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return the stable notice payload keys from design §6.4."""
        return {
            "dropped_messages": self.dropped_messages,
            "dropped_page_contexts": self.dropped_page_contexts,
            "clipped_tool_results": self.clipped_tool_results,
            "truncated_user_chars": self.truncated_user_chars,
            "truncated_attachments": self.truncated_attachments,
        }

    def lost_input(self) -> bool:
        """Return whether any provider input was removed or shortened."""
        return any(self.as_dict().values())


class AgentService:
    """Own conversation CRUD and the durable multi-step turn loop.

    The composition root builds exactly one instance per authenticated request.
    Its owner-scoped repository and tool service scope capture the acting
    ``user_id``/role, so the SSE turn loop keeps using that account for every
    later short transaction even after the request session is gone. A service
    instance must never be reused for another account.

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
        chat_attachments: ChatAttachmentServiceProtocol,
        server_timezone: str = "Asia/Taipei",
        active_provider: str = "",
        web_search_provider: str = "none",
        web_fetch_provider: str = "none",
        quota: AgentQuotaProtocol | None = None,
        model_plan: AgentModelPlanProtocol | None = None,
        model_status: str = "assigned",
    ) -> None:
        self.repository = repository
        self.chat_generator = chat_generator
        self.tool_registry = tool_registry
        self.default_provider = default_provider
        self.default_model = default_model
        self.config = config
        self.system_prompt_service = system_prompt_service
        self.chat_attachments = chat_attachments
        self.server_timezone = server_timezone
        # Provider availability is resolved by the composition root from the
        # account assignment. They are safe names only; keys and base URLs never
        # reach the agent service.
        self.active_provider = active_provider or default_provider or "none"
        self.web_search_provider = _web_provider_name(web_search_provider)
        self.web_fetch_provider = _web_provider_name(web_fetch_provider)
        # The composition root passes the captured account's allowance. It is
        # optional so isolated tests that exercise conversation mechanics keep
        # working with no quota policy.
        self.quota = quota
        # Provider calls use the current model, not the conversation's
        # creation-time metadata. Escalation is capped at one swap per run and
        # every generator in the plan comes from the same primary endpoint row.
        self._current_model = default_model
        self._model_plan = model_plan
        self._model_status = model_status
        self._escalations = 0
        self._budget_notice_emitted = False
        # The largest prompt size the provider has actually reported for the
        # current context segment. Local character estimation can undercount
        # CJK-heavy requests, so this floor is the second opinion that cannot be
        # ignored once a real response reports it.
        self._prompt_token_floor = 0

    async def _ensure_chat_allowed(self) -> None:
        if self.quota is not None and not await self.quota.chat_allowed():
            raise AgentUsageLimitExceededError()

    async def create_conversation(
        self,
        payload: AgentConversationCreateSchema,
        *,
        user_profile: UserProfile | None = None,
    ) -> AgentConversationSchema:
        provider = payload.provider or self.default_provider
        if provider not in {"deepseek", "openai-compatible", "anthropic"}:
            provider = "deepseek"
        model = payload.model or self.default_model or "deepseek-flash"
        now = utcnow()
        sections = await self.system_prompt_service.get_active_sections()
        system_data = build_system_data(
            provider=provider,
            model=model,
            sections=sections,
            user_profile=user_profile,
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
        entries, has_previous = await self.repository.list_latest_entries(
            conversation_id,
            limit=limit,
        )
        total = await self.repository.count_entries(conversation_id)
        page = _entry_page(
            conversation_id,
            entries,
            total,
            has_previous=has_previous,
        )
        base = _conversation_schema(conversation)
        last_page_context_key = await self.repository.last_page_context_key(conversation_id)
        return AgentConversationDetailSchema(
            **base.model_dump(),
            entries=page.entries,
            entries_total=page.total_results,
            entries_next_after_id=page.next_after_id,
            entries_has_more=page.has_more,
            entries_previous_before_id=page.previous_before_id,
            entries_has_previous=page.has_previous,
            last_page_context_key=last_page_context_key,
        )

    async def list_entries(
        self,
        conversation_id: int,
        *,
        after_id: int | None,
        before_id: int | None,
        limit: int,
    ) -> AgentEntryPageSchema:
        conversation = await self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise AgentConversationNotFoundError(conversation_id)
        if after_id is not None and before_id is not None:
            raise AgentInvalidEntryError(
                "Use after_id or before_id, not both."
            )
        total = await self.repository.count_entries(conversation_id)
        if before_id is not None:
            entries, has_previous = await self.repository.list_entries_before(
                conversation_id,
                before_id=before_id,
                limit=limit,
            )
            return _entry_page(
                conversation_id,
                entries,
                total,
                has_previous=has_previous,
            )
        entries, has_more = await self.repository.list_entries(
            conversation_id,
            after_id=after_id,
            limit=limit,
        )
        return _entry_page(conversation_id, entries, total, has_more=has_more)

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
        attachment_ids = tuple(payload.attachment_ids)
        attachments = await self.chat_attachments.prepare_for_message(attachment_ids)
        if not content and not attachments:
            raise AgentInvalidEntryError(
                "A message needs text or at least one temporary chat image."
            )
        await self._ensure_chat_allowed()
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
        if attachments:
            data["attachments"] = [attachment.to_entry_data() for attachment in attachments]
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
            attachment_ids=attachment_ids,
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
        await self._ensure_chat_allowed()
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
        draft = self._compaction_draft(
            _transcript_from_rows(rows),
            reason="manual",
            auto=False,
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
        if estimate_context_tokens(
            transcript,
            chars_per_token=self._chars_per_token(),
        ) <= self.config.compaction_threshold_tokens:
            return None
        return self._compaction_draft(
            transcript,
            reason="auto_context_threshold",
            auto=True,
        )

    async def _context_for_step(
        self,
        conversation_id: int,
        run_id: int,
        last_entry_id: int,
        last_compaction_entry_id: int | None,
    ) -> tuple[ProviderContext, int, int | None]:
        """Compact and fit the outbound context before a provider call.

        The pre-turn check in ``begin_message`` cannot see tool results added
        during this run. Re-check before every provider step so a long tool loop
        compacts instead of hitting the provider's context limit. The message
        ladder runs after the context is rebuilt and never raises a local
        context-limit error.
        """
        context: ProviderContext | None = None
        if self.config.auto_compaction_enabled:
            rows = await self.repository.load_context_entries(
                conversation_id,
                cutoff_entry_id=last_entry_id,
            )
            transcript = _transcript_from_rows(rows)
            active = compactable_context_entries(transcript)
            active_compactions = [
                entry.id for entry in active if entry.kind == KIND_COMPACTION
            ]
            latest_compaction = max(active_compactions) if active_compactions else None
            if last_compaction_entry_id is None:
                last_compaction_entry_id = latest_compaction
            # A compaction created by ``begin_message`` already carries the new
            # user/page input. Do not compact again until tool or assistant
            # entries have actually added new provider-visible work.
            pending_turn_only = latest_compaction is not None and not any(
                entry.id > latest_compaction
                and entry.kind not in {KIND_USER, KIND_PAGE_CONTEXT}
                for entry in active
            )
            if (
                not pending_turn_only
                and last_entry_id != last_compaction_entry_id
                and estimate_context_tokens(
                    transcript,
                    chars_per_token=self._chars_per_token(),
                )
                > self.config.compaction_threshold_tokens
            ):
                compacted = await self._compact_active_context(
                    conversation_id,
                    run_id,
                    last_entry_id,
                    reason="auto_context_threshold",
                )
                if compacted is not None:
                    context, last_entry_id = compacted
                    last_compaction_entry_id = last_entry_id
        if context is None:
            context = await self._context(
                conversation_id,
                last_entry_id,
                keep_plot_run_id=run_id,
            )
        return await self._enforce_context_budget(
            context,
            conversation_id=conversation_id,
            run_id=run_id,
            last_entry_id=last_entry_id,
            last_compaction_entry_id=last_compaction_entry_id,
        )

    async def _enforce_context_budget(
        self,
        context: ProviderContext,
        *,
        conversation_id: int,
        run_id: int,
        last_entry_id: int,
        last_compaction_entry_id: int | None,
    ) -> tuple[ProviderContext, int, int | None]:
        """Run the no-error overflow ladder for one outbound request.

        Order is fixed: forced compaction at 60% of the budget, page-context
        drop, tool-result clipping oldest-first, then outbound truncation of the
        current user message. The stored transcript is never modified; one
        ``ui.notice`` per run records what the model did not see.

        The entry check uses ``max(character estimate, reported prompt tokens)``
        so a provider-reported overshoot makes the next step compact or clip
        instead of repeating it. A forced compaction replaces the earlier
        transcript with a summary, so it starts a new estimate segment and the
        old floor is cleared. The stored transcript is unchanged.
        """
        budget = self.config.context_window_tokens
        chars_per_token = self._chars_per_token()
        if self._context_token_estimate(context) <= budget:
            return context, last_entry_id, last_compaction_entry_id
        target_tokens = max(1, math.floor(budget * _FORCED_COMPACTION_BUDGET_RATIO))
        forced = await self._forced_compaction_context(
            conversation_id,
            last_entry_id,
            target_tokens=target_tokens,
            keep_plot_run_id=run_id,
        )
        floor_tokens = self._prompt_token_floor
        if forced is not None:
            context = forced
            self._reset_provider_prompt_floor()
            floor_tokens = 0
        fitted, stats = _fit_provider_context(
            context,
            budget_tokens=budget,
            chars_per_token=chars_per_token,
            floor_tokens=floor_tokens,
        )
        if stats.lost_input() and not self._budget_notice_emitted:
            notice = EntryDraft(
                kind=KIND_NOTICE,
                messages=[],
                data={
                    "reason": "context_budget_truncated",
                    "budget_tokens": budget,
                    **stats.as_dict(),
                },
            )
            entries = await self.repository.append_tool_results(
                conversation_id=conversation_id,
                run_id=run_id,
                drafts=[notice],
                now=utcnow(),
            )
            if entries:
                last_entry_id = entries[-1].id
            self._budget_notice_emitted = True
            logger.info(
                "agent context budget applied conversation_id=%s run_id=%s "
                "budget_tokens=%d dropped_messages=%d dropped_page_contexts=%d "
                "clipped_tool_results=%d truncated_user_chars=%d "
                "truncated_attachments=%d",
                conversation_id,
                run_id,
                budget,
                stats.dropped_messages,
                stats.dropped_page_contexts,
                stats.clipped_tool_results,
                stats.truncated_user_chars,
                stats.truncated_attachments,
            )
        return fitted, last_entry_id, last_compaction_entry_id

    async def _forced_compaction_context(
        self,
        conversation_id: int,
        last_entry_id: int,
        *,
        target_tokens: int,
        keep_plot_run_id: int | None,
    ) -> ProviderContext | None:
        """Summarize the history before the current user into the outbound copy.

        The overflow backstop is intentionally ephemeral: it re-projects the
        request as "compaction summary + current user + anything after it" but
        appends no boundary. The current turn's input therefore stays complete
        in the outbound copy until the message ladder decides whether it must be
        truncated, and the stored transcript is never rewritten. Persisted
        compaction (threshold and provider-overflow) is still handled by
        ``_compact_active_context``.
        """
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=last_entry_id,
        )
        transcript = _transcript_from_rows(rows)
        active = active_context_entries(transcript)
        current_user_index = next(
            (
                index
                for index in range(len(active) - 1, -1, -1)
                if active[index].kind == KIND_USER
            ),
            None,
        )
        if current_user_index is None:
            return None
        earlier = active[:current_user_index]
        if not compactable_context_entries(earlier):
            return None
        draft = self._compaction_draft(
            earlier,
            reason="forced_context_budget",
            auto=True,
            target_tokens=target_tokens,
        )
        system_entries = [
            entry for entry in transcript if entry.kind == KIND_SYSTEM
        ]
        tail = [*system_entries, *active[current_user_index:]]
        enriched = await self.chat_attachments.enrich_transcript(tail)
        tail_context = build_context(enriched, keep_plot_run_id=keep_plot_run_id)
        compaction_messages = [dict(message) for message in draft.messages]
        return replace(
            tail_context,
            messages=[*compaction_messages, *tail_context.messages],
        )

    def _compaction_draft(
        self,
        transcript: Sequence[TranscriptEntry],
        *,
        reason: str,
        auto: bool,
        target_tokens: int | None = None,
    ) -> EntryDraft:
        """Build one compaction entry, rendering the prompt only when forced.

        Threshold, manual, and provider-overflow compaction keep the legacy
        bytes exactly. Overflow-forced compaction additionally renders the
        operator's template and states the output cap it derived, because that
        entry is the one created to protect the budget.
        """
        if target_tokens is None:
            return build_compaction_draft(
                transcript,
                reason=reason,
                auto=auto,
                max_summary_chars=self.config.max_compaction_summary_chars,
                max_last_user_chars=self.config.max_compaction_last_user_chars,
            )
        chars_per_token = self._chars_per_token()
        draft = build_compaction_draft(
            transcript,
            reason=reason,
            auto=auto,
            max_summary_chars=self.config.max_compaction_summary_chars,
            max_last_user_chars=self.config.max_compaction_last_user_chars,
            target_tokens=target_tokens,
            chars_per_token=chars_per_token,
        )
        rendered = render_compaction_prompt(
            self.config.compaction_prompt,
            max_output_tokens=self.config.compaction_max_output_tokens,
            chars_per_token=chars_per_token,
            max_last_user_chars=self.config.max_compaction_last_user_chars,
        )
        content = draft.messages[0]["content"] if draft.messages else ""
        return replace(
            draft,
            messages=[{"role": "user", "content": f"{rendered}\n\n{content}"}],
        )

    def _chars_per_token(self) -> float:
        """Return the current model's catalog density (2.3 when unknown)."""
        return chars_per_token_for(self._current_model)

    def _note_provider_prompt_tokens(self, usage: Mapping[str, int]) -> None:
        """Remember the prompt size a successful provider call reported.

        The local estimate is character-based and necessarily approximate. Once
        a real response says the prompt was larger, the next budget check must
        treat that figure as a floor so an overshoot cannot be silently
        repeated. Only integers are trusted; a missing or zero value changes
        nothing.
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool):
            if prompt_tokens > self._prompt_token_floor:
                self._prompt_token_floor = prompt_tokens

    def _reset_provider_prompt_floor(self) -> None:
        """Forget a reported prompt size when a compaction starts a new segment.

        A compacted request no longer replays the old transcript, so its prompt
        size stops describing the new context. Keeping the floor would clip the
        fresh summary and user input against a request the provider will never
        see again.
        """
        self._prompt_token_floor = 0

    def _context_token_estimate(self, context: ProviderContext) -> int:
        """Return the conservative request estimate including the provider floor.

        ``max(character estimate, reported prompt tokens)`` is the value every
        budget decision uses. The character estimate stays the primary signal
        for a new segment; the floor only wins when a provider has already
        reported a larger request than the local ratio predicted.
        """
        return max(
            estimate_provider_context_tokens(
                context,
                chars_per_token=self._chars_per_token(),
            ),
            self._prompt_token_floor,
        )

    async def _compact_active_context(
        self,
        conversation_id: int,
        run_id: int,
        last_entry_id: int,
        *,
        reason: str,
    ) -> tuple[ProviderContext, int] | None:
        """Append a run-owned compaction boundary and rebuild the context."""
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=last_entry_id,
        )
        transcript = _transcript_from_rows(rows)
        if not compactable_context_entries(transcript):
            return None
        draft = self._compaction_draft(
            transcript,
            reason=reason,
            auto=True,
        )
        entry = await self.repository.append_run_compaction(
            conversation_id=conversation_id,
            run_id=run_id,
            draft=draft,
            now=utcnow(),
        )
        # The persisted boundary starts a new context segment. The previous
        # provider-reported prompt size described the hidden transcript, not the
        # summary the next request will send.
        self._reset_provider_prompt_floor()
        return (
            await self._context(
                conversation_id,
                entry.id,
                keep_plot_run_id=run_id,
            ),
            entry.id,
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
        # The reported prompt floor is scoped to this run. A resumed approval
        # starts a fresh loop snapshot, so it re-learns the floor from the first
        # successful call in the resumed segment.
        self._reset_provider_prompt_floor()
        terminal = False
        loop_started = time.monotonic()
        completed_steps = 0
        logger.info(
            "agent run started run_id=%s conversation_id=%s provider=%s "
            "model=%s resumed=%s max_steps=%d page_context=%s",
            run_id,
            conversation_id,
            turn.conversation.provider,
            turn.conversation.model or "-",
            resumed,
            self.config.max_steps,
            turn.page_context_entry_id is not None,
        )

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
            last_compaction_entry_id: int | None = None
            context_overflow_retried = False
            rendered_plot_titles: set[str] = set()
            duplicate_plot_count = 0
            invalid_arguments_streak = 0
            pending_retry_notice: str | None = None

            for step in range(start_step, self.config.max_steps + 1):
                if await self.repository.is_abort_requested(conversation_id, run_id):
                    await self._best_effort_cancel(turn, last_entry_id)
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return

                if self.quota is not None and not await self.quota.chat_allowed():
                    # The account may have exhausted its grant in an earlier
                    # step of this same run. Stop before the provider call and
                    # persist the same failure shape as a provider error so the
                    # transcript and UI stay auditable.
                    detail = AgentUsageLimitExceededError.DETAIL
                    last_entry_id = await self._append_failure_assistant(
                        turn,
                        last_entry_id,
                        "usage_limit_exceeded",
                        detail,
                        step,
                    )
                    await self._fail_run(
                        turn,
                        last_entry_id,
                        "usage_limit_exceeded",
                        detail,
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
                        {"code": "usage_limit_exceeded", "detail": detail},
                    )
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_FAILED},
                    )
                    return

                try:
                    (
                        context,
                        last_entry_id,
                        last_compaction_entry_id,
                    ) = await self._context_for_step(
                        conversation_id,
                        run_id,
                        last_entry_id,
                        last_compaction_entry_id,
                    )
                except AgentRunNotActiveError:
                    terminal = True
                    yield AgentStreamEvent(
                        "run_end",
                        {"run_id": run_id, "status": RUN_CANCELLED},
                    )
                    return

                step_started = time.monotonic()
                logger.info(
                    "agent step started run_id=%s conversation_id=%s step=%d "
                    "messages=%d tools=%d message_chars=%d tool_chars=%d",
                    run_id,
                    conversation_id,
                    step,
                    len(context.messages) + (1 if context.system_message.get("content") else 0),
                    len(context.tools),
                    _context_chars([context.system_message, *context.messages]),
                    len(json.dumps(context.tools, ensure_ascii=False)),
                )
                yield AgentStreamEvent(
                    "message_start",
                    {"entry_id": None, "kind": KIND_ASSISTANT, "role": "assistant"},
                )
                output_limit_retries = 0
                retry_usage: dict[str, int] = {}
                retry_next_step = False
                while True:
                    agent_status = self._agent_status_message(
                        context,
                        retry_notice=pending_retry_notice,
                    )
                    pending_retry_notice = None
                    completion = _CompletionOutcome()
                    async for event in self._completion_events(
                        context,
                        self._current_model,
                        completion,
                        run_id=run_id,
                        step=step,
                        agent_status=agent_status,
                    ):
                        yield event
                    result = completion.result
                    provider_error = completion.error
                    if result is None:
                        if (
                            isinstance(provider_error, AiContextWindowError)
                            and self.config.auto_compaction_enabled
                            and not context_overflow_retried
                        ):
                            try:
                                compacted = await self._compact_active_context(
                                    conversation_id,
                                    run_id,
                                    last_entry_id,
                                    reason="provider_context_overflow",
                                )
                            except AgentRunNotActiveError:
                                terminal = True
                                yield AgentStreamEvent(
                                    "run_end",
                                    {"run_id": run_id, "status": RUN_CANCELLED},
                                )
                                return
                            if compacted is not None:
                                context_overflow_retried = True
                                context, last_entry_id = compacted
                                last_compaction_entry_id = last_entry_id
                                pending_retry_notice = render_context_overflow_notice()
                                retry_next_step = True
                                break
                        if isinstance(provider_error, AiContextWindowError):
                            escalated, last_entry_id = await self._maybe_escalate(
                                turn,
                                "context_window",
                                last_entry_id=last_entry_id,
                            )
                            if escalated:
                                retry_next_step = True
                                break
                        (
                            last_entry_id,
                            provider_code,
                            provider_detail,
                        ) = await self._append_provider_failure(
                            turn,
                            last_entry_id,
                            provider_error,
                            step,
                            partial_text=completion.text,
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
                    if finish_reason == "refusal":
                        # A refusal is a model/endpoint signal, not a user input
                        # error. One same-endpoint escalation gets one chance; if
                        # it is unavailable, a refusal that carries text is still
                        # a valid answer and an empty one stays unusable.
                        escalated, last_entry_id = await self._maybe_escalate(
                            turn,
                            "refusal",
                            last_entry_id=last_entry_id,
                        )
                        if escalated:
                            _merge_usage(retry_usage, result.usage)
                            continue
                        if not result.text.strip():
                            finish_reason = None
                    if finish_reason is not None:
                        if retry_usage:
                            merged_usage = dict(retry_usage)
                            _merge_usage(merged_usage, result.usage)
                            result = replace(result, usage=merged_usage)
                            retry_usage = {}
                        break

                    logger.warning(
                        "agent completion unusable run_id=%s conversation_id=%s "
                        "step=%d finish_reason=%s completion_tokens=%d "
                        "text_chars=%d tool_calls=%d",
                        run_id,
                        conversation_id,
                        step,
                        result.finish_reason or "-",
                        result.usage.get("completion_tokens", 0),
                        len(result.text),
                        len(result.tool_calls),
                    )
                    if (
                        (result.finish_reason or "").lower() == "length"
                        and not result.text.strip()
                    ):
                        # A completion cut off at the output cap produced no
                        # visible text, so the same step can be retried once.
                        _merge_usage(retry_usage, result.usage)
                        if output_limit_retries < 1:
                            output_limit_retries += 1
                            pending_retry_notice = render_output_limit_notice()
                            continue
                        escalated, last_entry_id = await self._maybe_escalate(
                            turn,
                            "output_limit",
                            last_entry_id=last_entry_id,
                        )
                        if escalated:
                            continue
                        async for event in self._stream_assistant_text(
                            turn,
                            last_entry_id,
                            text=_output_limit_text(
                                self.chat_generator.max_output_tokens
                            ),
                            step=step,
                            usage=retry_usage,
                            cache_prefix_hash=context.cache_prefix_hash,
                            emit_message_start=True,
                            reasoning=completion.reasoning,
                        ):
                            yield event
                        terminal = True
                        return

                    completion_error: Exception
                    if (result.finish_reason or "").lower() == "length":
                        # Non-recoverable truncation (for example visible text was
                        # already emitted) keeps the actionable output_limit code.
                        completion_error = AgentOutputLimitError()
                    else:
                        completion_error = RuntimeError(
                            "truncated or malformed completion"
                        )
                    if not isinstance(completion_error, AgentOutputLimitError):
                        escalated, last_entry_id = await self._maybe_escalate(
                            turn,
                            "unusable_completion",
                            last_entry_id=last_entry_id,
                        )
                        if escalated:
                            _merge_usage(retry_usage, result.usage)
                            continue
                    (
                        last_entry_id,
                        provider_code,
                        provider_detail,
                    ) = await self._append_provider_failure(
                        turn,
                        last_entry_id,
                        completion_error,
                        step,
                        usage=result.usage,
                        partial_text=result.text,
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

                if retry_next_step:
                    continue
                assert result is not None
                assert finish_reason is not None

                completed_steps += 1
                logger.info(
                    "agent step completed run_id=%s conversation_id=%s step=%d "
                    "duration_ms=%d finish_reason=%s text_chars=%d "
                    "tool_calls=%d tool_names=%s prompt_tokens=%d "
                    "completion_tokens=%d total_tokens=%d cached_tokens=%d",
                    run_id,
                    conversation_id,
                    step,
                    int((time.monotonic() - step_started) * 1000),
                    finish_reason,
                    len(result.text),
                    len(result.tool_calls),
                    ",".join(call.name for call in result.tool_calls) or "-",
                    result.usage.get("prompt_tokens", 0),
                    result.usage.get("completion_tokens", 0),
                    result.usage.get("total_tokens", 0),
                    result.usage.get("prompt_cache_hit_tokens", 0),
                )
                assistant_message = _assistant_message(result)
                assistant_data = _assistant_data(
                    result,
                    turn,
                    step,
                    finish_reason,
                    context.cache_prefix_hash,
                    model=self._current_model,
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
                        usage=result.usage,
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
                    logger.info(
                        "agent run completed run_id=%s conversation_id=%s "
                        "duration_ms=%d steps=%d finish_reason=%s "
                        "last_entry_id=%s",
                        run_id,
                        conversation_id,
                        int((time.monotonic() - loop_started) * 1000),
                        completed_steps,
                        finish_reason,
                        last_entry_id,
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

                batch_size = len(calls)
                parallel = self.config.parallel_tools_enabled and batch_size > 1
                planned: list[tuple[ChatToolCall, ToolOutcome] | None] = [None] * batch_size
                eligible_indices: list[int] = []
                approval_specs: list[tuple[int, ChatToolCall, dict[str, Any]]] = []
                backend_approved_indices: set[int] = set()
                batch_plot_titles: set[str] = set()
                for index, call in enumerate(calls):
                    yield AgentStreamEvent(
                        "tool_start",
                        {
                            "entry_id": None,
                            "tool_call_id": call.call_id,
                            "name": call.name,
                            "arguments": display_arguments(call.name, call.arguments),
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
                    plot_title = (
                        _plot_title_key(call.arguments)
                        if call.name == "render_plot"
                        else None
                    )
                    if plot_title is not None and (
                        plot_title in rendered_plot_titles
                        or plot_title in batch_plot_titles
                    ):
                        # The same title already rendered in this run. Suppress
                        # the call so the UI cannot show a second identical chart.
                        duplicate_plot_count += 1
                        planned[index] = (
                            call,
                            _duplicate_plot_outcome(call.arguments.get("title")),
                        )
                        continue
                    if plot_title is not None:
                        batch_plot_titles.add(plot_title)
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

                for planned_outcome in planned:
                    if planned_outcome is None:
                        continue
                    planned_call, planned_result = planned_outcome
                    if planned_call.name != "render_plot":
                        continue
                    plot_title = _plot_title_key(planned_call.arguments)
                    if plot_title is not None and _is_rendered_plot(planned_result):
                        rendered_plot_titles.add(plot_title)

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
                    logger.info(
                        "agent run waiting run_id=%s conversation_id=%s "
                        "duration_ms=%d steps=%d approvals=%d last_entry_id=%s",
                        run_id,
                        conversation_id,
                        int((time.monotonic() - loop_started) * 1000),
                        completed_steps,
                        len(approvals),
                        last_entry_id,
                    )
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

                for _call, outcome in outcomes:
                    if outcome.error_code in _INVALID_ARGUMENT_ERROR_CODES:
                        invalid_arguments_streak += 1
                    else:
                        invalid_arguments_streak = 0

                if invalid_arguments_streak >= _INVALID_ARGUMENTS_TEXT_ONLY_THRESHOLD:
                    # One same-endpoint escalation is preferred over removing
                    # tools; a successful arguments escalation resets the streak.
                    escalated, last_entry_id = await self._maybe_escalate(
                        turn,
                        "invalid_tool_arguments",
                        last_entry_id=last_entry_id,
                    )
                    if escalated:
                        invalid_arguments_streak = 0
                        continue
                    # The same invalid call survived the retry notice, so offer
                    # no tools for one call and let the model answer in text.
                    # Rebuild the context first so the final call sees the tool
                    # results appended above, not the pre-step snapshot.
                    try:
                        (
                            context,
                            last_entry_id,
                            last_compaction_entry_id,
                        ) = await self._context_for_step(
                            conversation_id,
                            run_id,
                            last_entry_id,
                            last_compaction_entry_id,
                        )
                    except AgentRunNotActiveError:
                        terminal = True
                        yield AgentStreamEvent(
                            "run_end",
                            {"run_id": run_id, "status": RUN_CANCELLED},
                        )
                        return
                    async for event in self._stream_text_only_answer(
                        turn,
                        context,
                        last_entry_id,
                        step=step,
                    ):
                        yield event
                    terminal = True
                    return
                if invalid_arguments_streak >= _INVALID_ARGUMENTS_NOTICE_THRESHOLD:
                    pending_retry_notice = render_invalid_arguments_notice()

                if duplicate_plot_count >= 2:
                    # Loop breaker: the model received one duplicate notice and
                    # still repeated the call, so answer in text and stop.
                    async for event in self._stream_assistant_text(
                        turn,
                        last_entry_id,
                        text=DUPLICATE_PLOT_STOP_TEXT,
                        step=step,
                        usage={},
                        cache_prefix_hash=context.cache_prefix_hash,
                        emit_message_start=True,
                        reasoning=completion.reasoning,
                    ):
                        yield event
                    terminal = True
                    return

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
                plot_limits=self._plot_limits(),
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

    def _plot_limits(self) -> PlotLimits:
        """Return the snapshot's render_plot budgets for one tool call."""
        return PlotLimits(
            max_points=self.config.max_plot_points,
            max_bytes=self.config.max_plot_bytes,
            max_nodes=self.config.max_plot_nodes,
        )

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
        started = time.monotonic()
        argument_keys = ",".join(sorted(call.arguments)) or "-"
        logger.info(
            "agent tool started tool=%s call_id=%s approved=%s "
            "parse_error=%s argument_keys=%s argument_chars=%d",
            call.name,
            call.call_id,
            approved,
            call.parse_error is not None,
            argument_keys,
            len(call.raw_arguments),
        )
        try:
            outcome = await self.tool_registry.execute(
                call.name,
                call.arguments,
                call_id=call.call_id,
                max_chars=self.config.max_tool_result_chars,
                parse_error=call.parse_error,
                approved=approved,
                plot_limits=self._plot_limits(),
            )
        except Exception:
            logger.exception(
                "agent tool crashed tool=%s call_id=%s duration_ms=%d",
                call.name,
                call.call_id,
                int((time.monotonic() - started) * 1000),
            )
            raise
        logger.info(
            "agent tool completed tool=%s call_id=%s status=%s "
            "error_code=%s duration_ms=%d result_chars=%d",
            call.name,
            call.call_id,
            outcome.status,
            outcome.error_code or "-",
            int((time.monotonic() - started) * 1000),
            len(outcome.content),
        )
        return outcome

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
        *,
        run_id: int,
        step: int,
        agent_status: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Run one provider call and yield transport-only text deltas.

        ``agent_status`` is the provider-only status feedback block. It is
        always the single last message, after the frozen system prefix and every
        replayed context message, so the cached prefix and the tool-call
        adjacency stay byte-identical. ``tools`` overrides the context's tool
        list for the bounded text-only loop breaker; ``None`` sends the normal
        snapshot.

        A retryable upstream failure is retried automatically only while no
        text delta has reached the client. Once a token has been streamed, a
        retry could duplicate visible output, so the failure is returned and
        the normal durable retry path takes over.
        """
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        provider_messages = _provider_messages(context, agent_status)
        provider_tools = context.tools if tools is None else tools
        max_attempts = len(_PROVIDER_RETRY_DELAYS_SECONDS) + 1

        async def run() -> None:
            for attempt in range(1, max_attempts + 1):
                emitted = False

                async def on_delta(delta: str) -> None:
                    nonlocal emitted
                    emitted = True
                    outcome.text += delta
                    await queue.put(("delta", delta))

                async def on_reasoning(delta: str) -> None:
                    nonlocal emitted
                    emitted = True
                    outcome.reasoning += delta
                    await queue.put(("reasoning", delta))

                attempt_started = time.monotonic()
                try:
                    result = await self.chat_generator.complete_chat(
                        provider_messages,
                        provider_tools,
                        model=model,
                        stream=True,
                        on_text_delta=on_delta,
                        on_reasoning_delta=on_reasoning,
                    )
                except AiProviderError as exc:
                    duration_ms = int((time.monotonic() - attempt_started) * 1000)
                    if exc.retryable and not emitted and attempt < max_attempts:
                        delay = _PROVIDER_RETRY_DELAYS_SECONDS[attempt - 1]
                        logger.warning(
                            "provider call retry scheduled run_id=%s step=%s "
                            "provider=deepseek model=%s attempt=%d "
                            "max_attempts=%d delay_s=%s duration_ms=%d "
                            "status=%s request_id=%s error_code=%s "
                            "error_message=%r",
                            run_id,
                            step,
                            model or "-",
                            attempt,
                            max_attempts,
                            delay,
                            duration_ms,
                            exc.status_code,
                            exc.provider_request_id or "-",
                            exc.provider_error_code or "-",
                            str(exc),
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(
                        "provider call failed run_id=%s step=%s "
                        "provider=deepseek model=%s attempt=%d max_attempts=%d "
                        "streamed_text=%s duration_ms=%d status=%s "
                        "request_id=%s error_type=%s error_code=%s "
                        "error_message=%r",
                        run_id,
                        step,
                        model or "-",
                        attempt,
                        max_attempts,
                        emitted,
                        duration_ms,
                        exc.status_code,
                        exc.provider_request_id or "-",
                        type(exc).__name__,
                        exc.provider_error_code or "-",
                        str(exc),
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    await queue.put(("error", exc))
                    return
                except Exception as exc:
                    logger.exception(
                        "provider call failed run_id=%s step=%s "
                        "provider=deepseek model=%s attempt=%d max_attempts=%d "
                        "streamed_text=%s duration_ms=%d error_type=%s",
                        run_id,
                        step,
                        model or "-",
                        attempt,
                        max_attempts,
                        emitted,
                        int((time.monotonic() - attempt_started) * 1000),
                        type(exc).__name__,
                    )
                    await queue.put(("error", exc))
                    return
                logger.info(
                    "provider call succeeded run_id=%s step=%s "
                    "provider=deepseek model=%s attempt=%d duration_ms=%d "
                    "finish_reason=%s text_chars=%d tool_calls=%d",
                    run_id,
                    step,
                    model or "-",
                    attempt,
                    int((time.monotonic() - attempt_started) * 1000),
                    result.finish_reason,
                    len(result.text),
                    len(result.tool_calls),
                )
                self._note_provider_prompt_tokens(result.usage)
                await queue.put(("result", result))
                return

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
                if kind == "reasoning":
                    yield AgentStreamEvent(
                        "reasoning_delta",
                        {"entry_id": None, "delta": payload},
                    )
                    continue
                if kind == "result":
                    outcome.result = payload if isinstance(payload, ChatResult) else None
                    if outcome.result is None:
                        outcome.error = RuntimeError("provider returned an invalid result")
                    elif outcome.result.reasoning and not outcome.reasoning:
                        # A provider may report reasoning only in the final
                        # result (no streamed deltas). Keep it without inventing
                        # a duplicate stream.
                        outcome.reasoning = outcome.result.reasoning
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

    def _agent_status_message(
        self,
        context: ProviderContext,
        *,
        retry_notice: str | None,
    ) -> str:
        """Render the provider-only status message for this exact request.

        ``context_used`` covers the complete ordered request assembled by
        ``_provider_messages``: the frozen system message, every replayed context
        message in entry order, and this trailing block. The estimate uses the
        same chars-per-token ratio as the budget ladder and runs after chat-image
        enrichment, so raw base64 image payloads are stripped. It is a
        conservative estimate, not a provider-exact token count: a reported
        prompt size from an earlier successful call in the same context segment
        is used as a floor, so the block never claims less than the provider
        already observed.

        Because the block renders its own estimate, its digit count can change
        the total. A bounded fixed-point loop re-estimates after each render
        until the number stops moving. Only the deterministic estimator runs;
        this never calls a provider or a tokenizer.
        """
        chars_per_token = self._chars_per_token()
        limit = self.config.context_window_tokens
        compaction_at = self.config.compaction_threshold_tokens
        total = max(
            estimate_provider_context_tokens(
                context,
                strip_image_data=True,
                chars_per_token=chars_per_token,
            ),
            self._prompt_token_floor,
        )

        def render(used: int) -> str:
            return render_agent_status(
                AgentStatus(
                    max_tool_result_chars=self.config.max_tool_result_chars,
                    max_page_context_chars=self.config.max_page_context_chars,
                    max_expression_chars=MAX_EXPRESSION_CHARS,
                    output_limit_tokens=self.chat_generator.max_output_tokens,
                    retry_notice=retry_notice,
                    context_used=used,
                    context_limit=limit,
                    context_remaining=max(0, limit - used),
                    compaction_at=compaction_at,
                    compaction_in=max(0, compaction_at - used),
                )
            )

        block = render(total)
        for _ in range(_AGENT_STATUS_ESTIMATE_ATTEMPTS):
            with_block = max(
                _estimated_provider_request_tokens(
                    context,
                    block,
                    chars_per_token=chars_per_token,
                ),
                self._prompt_token_floor,
            )
            if with_block == total:
                return block
            total = with_block
            block = render(total)
        return block

    async def _stream_assistant_text(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        *,
        text: str,
        step: int,
        usage: dict[str, int],
        cache_prefix_hash: str,
        emit_message_start: bool,
        reasoning: str = "",
    ) -> AsyncIterator[AgentStreamEvent]:
        """Persist a normal assistant answer and complete the run.

        Recoverable limit outcomes use this path: the user receives an
        explanation, the run completes normally, and no error entry is written.
        ``reasoning`` is carried only when a caller already has provider
        reasoning for this exact completion; otherwise it stays empty.
        """
        run_id = turn.run.id
        conversation_id = turn.conversation.id
        if emit_message_start:
            yield AgentStreamEvent(
                "message_start",
                {"entry_id": None, "kind": KIND_ASSISTANT, "role": "assistant"},
            )
        yield AgentStreamEvent(
            "message_delta",
            {"entry_id": None, "delta": text},
        )
        result = ChatResult(
            text=text,
            finish_reason="stop",
            model=self._current_model,
            usage=dict(usage),
            reasoning=reasoning,
        )
        try:
            entry = await self.repository.append_assistant(
                conversation_id=conversation_id,
                run_id=run_id,
                draft=EntryDraft(
                    kind=KIND_ASSISTANT,
                    messages=[_assistant_message(result)],
                    data=_assistant_data(
                        result,
                        turn,
                        step,
                        "stop",
                        cache_prefix_hash,
                        model=self._current_model,
                    ),
                ),
                now=utcnow(),
                usage=usage or None,
            )
        except AgentRunNotActiveError:
            await self._best_effort_cancel(turn, last_entry_id)
            yield AgentStreamEvent(
                "run_end",
                {"run_id": run_id, "status": RUN_CANCELLED},
            )
            return
        yield AgentStreamEvent(
            "message_end",
            {
                "entry_id": entry.id,
                "usage": dict(usage),
                "finish_reason": "stop",
            },
        )
        await self.repository.complete_run(
            conversation_id=conversation_id,
            run_id=run_id,
            last_entry_id=entry.id,
            now=utcnow(),
        )
        logger.info(
            "agent run completed run_id=%s conversation_id=%s step=%d "
            "finish_reason=stop last_entry_id=%s",
            run_id,
            conversation_id,
            step,
            entry.id,
        )
        yield AgentStreamEvent(
            "run_end",
            {"run_id": run_id, "status": RUN_COMPLETED},
        )

    async def _stream_text_only_answer(
        self,
        turn: AgentTurnState,
        context: ProviderContext,
        last_entry_id: int,
        *,
        step: int,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Run one provider call with no tools and complete the run with its text.

        This is the bounded loop breaker for three consecutive rejected tool
        calls. A provider offered no tools can only answer in text, so the user
        receives a normal explanation instead of a failed run or another
        invalid call. Only a real provider failure on this final call uses the
        ordinary error path.
        """
        run_id = turn.run.id
        conversation_id = turn.conversation.id
        yield AgentStreamEvent(
            "message_start",
            {"entry_id": None, "kind": KIND_ASSISTANT, "role": "assistant"},
        )
        # The caller rebuilt the context immediately before this call, but the
        # ladder runs here as well so a text-only answer can never exceed the
        # local budget.
        context, last_entry_id, _last_compaction = await self._enforce_context_budget(
            context,
            conversation_id=conversation_id,
            run_id=run_id,
            last_entry_id=last_entry_id,
            last_compaction_entry_id=None,
        )
        completion = _CompletionOutcome()
        async for event in self._completion_events(
            context,
            self._current_model,
            completion,
            run_id=run_id,
            step=step,
            agent_status=self._agent_status_message(
                context,
                retry_notice=render_invalid_arguments_notice(),
            ),
            tools=[],
        ):
            yield event

        result = completion.result
        if result is not None and result.tool_calls:
            # No tools were offered, so a stray call cannot run. Keep whatever
            # text the completion produced and finish as a normal answer.
            result = replace(result, tool_calls=[], finish_reason="stop")
        finish_reason = _normalize_finish(result) if result is not None else None
        if result is None or finish_reason is None:
            error = completion.error or RuntimeError("empty text-only completion")
            (
                last_entry_id,
                provider_code,
                provider_detail,
            ) = await self._append_provider_failure(
                turn,
                last_entry_id,
                error,
                step,
                partial_text=completion.text,
            )
            await self._fail_run(
                turn,
                last_entry_id,
                provider_code,
                provider_detail,
            )
            yield AgentStreamEvent(
                "message_end",
                {"entry_id": last_entry_id, "usage": {}, "finish_reason": "error"},
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

        try:
            entry = await self.repository.append_assistant(
                conversation_id=conversation_id,
                run_id=run_id,
                draft=EntryDraft(
                    kind=KIND_ASSISTANT,
                    messages=[_assistant_message(result)],
                    data=_assistant_data(
                        result,
                        turn,
                        step,
                        finish_reason,
                        context.cache_prefix_hash,
                        model=self._current_model,
                    ),
                ),
                now=utcnow(),
                usage=result.usage,
            )
        except AgentRunNotActiveError:
            await self._best_effort_cancel(turn, last_entry_id)
            yield AgentStreamEvent(
                "run_end",
                {"run_id": run_id, "status": RUN_CANCELLED},
            )
            return
        yield AgentStreamEvent(
            "message_end",
            {
                "entry_id": entry.id,
                "usage": dict(result.usage),
                "finish_reason": finish_reason,
            },
        )
        await self.repository.complete_run(
            conversation_id=conversation_id,
            run_id=run_id,
            last_entry_id=entry.id,
            now=utcnow(),
        )
        logger.info(
            "agent run completed run_id=%s conversation_id=%s step=%s "
            "finish_reason=%s last_entry_id=%s reason=invalid_arguments_text_only",
            run_id,
            conversation_id,
            step,
            finish_reason,
            entry.id,
        )
        yield AgentStreamEvent(
            "run_end",
            {"run_id": run_id, "status": RUN_COMPLETED},
        )

    async def _context(
        self,
        conversation_id: int,
        cutoff_entry_id: int | None,
        *,
        keep_plot_run_id: int | None = None,
    ) -> ProviderContext:
        rows = await self.repository.load_context_entries(
            conversation_id,
            cutoff_entry_id=cutoff_entry_id,
        )
        transcript = _transcript_from_rows(rows)
        enriched = await self.chat_attachments.enrich_transcript(transcript)
        return build_context(enriched, keep_plot_run_id=keep_plot_run_id)

    async def _append_failure_assistant(
        self,
        turn: AgentTurnState,
        last_entry_id: int,
        code: str,
        detail: str,
        step: int,
        usage: dict[str, int] | None = None,
        partial_text: str = "",
    ) -> int:
        data: dict[str, Any] = {
            "finish_reason": "error",
            "error": {"code": code, "detail": detail},
            "model": self._current_model,
            "provider": turn.conversation.provider,
            "step": step,
        }
        if partial_text:
            data["partial"] = True
        if usage is not None:
            data["usage"] = dict(usage)
        draft = EntryDraft(
            kind=KIND_ASSISTANT,
            messages=[{"role": "assistant", "content": partial_text}],
            data=data,
        )
        try:
            entry = await self.repository.append_assistant(
                conversation_id=turn.conversation.id,
                run_id=turn.run.id,
                draft=draft,
                now=utcnow(),
                usage=usage,
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
        usage: dict[str, int] | None = None,
        partial_text: str = "",
    ) -> tuple[int, str, str]:
        if isinstance(error, AiNotConfiguredError):
            if self._model_status == "inactive":
                code = "provider_inactive"
                detail = (
                    "The assigned chat endpoint is not active or has no usable "
                    "API key."
                )
            elif self._model_status == "missing":
                code = "model_not_assigned"
                detail = "No chat model is assigned to this account."
            else:
                code = "not_configured"
                detail = "No chat provider is configured."
        elif isinstance(error, AgentOutputLimitError):
            code = "output_limit"
            detail = (
                "The model reached its output token limit while generating the response. "
                "Ask for a smaller or simpler result (for example, fewer plot points), "
                "then retry."
            )
        else:
            code = "provider_error"
            if isinstance(error, AiProviderError) and error.retryable:
                detail = (
                    "The chat provider is temporarily unavailable. "
                    "Try again in a moment."
                )
            else:
                detail = "The chat provider failed."
        logger.error(
            "agent provider failure run_id=%s conversation_id=%s step=%s "
            "provider=%s model=%s error_type=%s retryable=%s status=%s "
            "request_id=%s provider_error_code=%s error_message=%r",
            turn.run.id,
            turn.conversation.id,
            step,
            turn.conversation.provider,
            turn.conversation.model or "-",
            type(error).__name__ if error is not None else "unknown",
            isinstance(error, AiProviderError) and error.retryable,
            error.status_code if isinstance(error, AiProviderError) else None,
            (error.provider_request_id if isinstance(error, AiProviderError) else None)
            or "-",
            (error.provider_error_code if isinstance(error, AiProviderError) else None)
            or "-",
            str(error) if error is not None else "unknown",
            exc_info=(
                (type(error), error, error.__traceback__)
                if error is not None
                else None
            ),
        )
        entry_id = await self._append_failure_assistant(
            turn,
            last_entry_id,
            code,
            detail,
            step,
            usage=usage,
            partial_text=partial_text,
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
                    "arguments": display_arguments(call.name, call.arguments),
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
        logger.warning(
            "agent run failed run_id=%s conversation_id=%s code=%s detail=%r last_entry_id=%s",
            turn.run.id,
            turn.conversation.id,
            code,
            detail,
            last_entry_id,
        )
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

    async def _maybe_escalate(
        self,
        turn: AgentTurnState,
        reason: str,
        *,
        last_entry_id: int,
    ) -> tuple[bool, int]:
        """Swap to the next catalog tier once, on the same endpoint row.

        The kill switch, the one-per-run cap, and the plan's single target are
        all checked before any notice or client is built. A failed or cancelled
        run leaves the current generator untouched. A successful swap appends
        one ``ui.notice`` with the transition; no provider-visible message is
        sent.
        """
        if (
            self._model_plan is None
            or not self.config.model_escalation_enabled
            or self._escalations >= 1
        ):
            return False, last_entry_id
        next_model = self._model_plan.next_model(self._current_model)
        if next_model is None:
            return False, last_entry_id
        previous_model = self._current_model
        try:
            generator = self._model_plan.generator_for(next_model)
        except Exception:
            logger.exception(
                "agent escalation client build failed run_id=%s model=%s",
                turn.run.id,
                next_model,
            )
            return False, last_entry_id
        notice = EntryDraft(
            kind=KIND_NOTICE,
            messages=[],
            data={
                "reason": reason,
                "from_model": previous_model,
                "to_model": next_model,
            },
        )
        try:
            entries = await self.repository.append_tool_results(
                conversation_id=turn.conversation.id,
                run_id=turn.run.id,
                drafts=[notice],
                now=utcnow(),
            )
        except AgentRunNotActiveError:
            return False, last_entry_id
        self.chat_generator = generator
        self._current_model = next_model
        self._escalations += 1
        new_last_entry_id = entries[-1].id if entries else last_entry_id
        logger.info(
            "agent model escalated run_id=%s conversation_id=%s reason=%s "
            "from_model=%s to_model=%s last_entry_id=%s",
            turn.run.id,
            turn.conversation.id,
            reason,
            previous_model or "-",
            next_model,
            new_last_entry_id,
        )
        return True, new_last_entry_id

    def _ensure_configured(self) -> None:
        """Fail before the SSE response starts when the slot cannot run.

        A missing assignment and an inactive/keyless endpoint are configuration
        errors with their own stable codes. A ``NullTextGenerator`` must never
        reach a completion call, because the null client would raise a generic
        not-configured error instead of naming the broken slot.
        """
        if self._model_status == "missing":
            raise ModelNotAssignedError()
        if self._model_status == "inactive":
            raise ProviderInactiveError()
        if not self.chat_generator.configured:
            raise AgentNotConfiguredError()


def _provider_messages(
    context: ProviderContext,
    agent_status: str,
) -> list[dict[str, Any]]:
    """Return the exact provider message list for one agent step.

    The order is absolute: the frozen system prompt first, then the replayed
    context messages without reordering, then exactly one trailing agent status
    message. The status block is provider-only input and is never persisted.
    """
    messages: list[dict[str, Any]] = []
    if context.system_message.get("content"):
        messages.append(context.system_message)
    messages.extend(context.messages)
    messages.append({"role": "system", "content": agent_status})
    return messages


def _estimated_provider_request_tokens(
    context: ProviderContext,
    agent_status: str,
    *,
    chars_per_token: float,
) -> int:
    """Estimate tokens for the exact ordered request including the status block.

    This assumes the ``_provider_messages`` order: the frozen system message,
    every replayed context message in entry order, then ``agent_status`` as the
    final system message. Image data URLs are stripped because the status block
    is composed after chat-image enrichment and its budget must not count raw
    base64 payload bytes.
    """
    return estimate_provider_context_tokens(
        replace(
            context,
            messages=[
                *context.messages,
                {"role": "system", "content": agent_status},
            ],
        ),
        strip_image_data=True,
        chars_per_token=chars_per_token,
    )


def _context_chars(messages: Sequence[Mapping[str, Any]]) -> int:
    """Count provider text without serializing base64 image payloads for a log."""
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    total += len(text)
                elif part.get("type") == "image_url":
                    total += 32
    return total


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
    *,
    has_more: bool = False,
    has_previous: bool = False,
) -> AgentEntryPageSchema:
    entries = [_entry_schema(row) for row in rows]
    return AgentEntryPageSchema(
        conversation_id=conversation_id,
        total_results=total,
        entries=entries,
        next_after_id=entries[-1].id if has_more and entries else None,
        has_more=has_more,
        previous_before_id=entries[0].id if has_previous and entries else None,
        has_previous=has_previous,
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
    """Serialize one persisted assistant call with display-only arguments.

    A render_plot figure is stored once, in the tool result's
    ``data.plot.figure``. The assistant message keeps only the title and
    caption, and the provider projection restores the figure for the run that
    rendered it. Other tools persist their full arguments.
    """
    if call.parse_error is not None and call.raw_arguments:
        return call.raw_arguments
    return json.dumps(
        display_arguments(call.name, call.arguments),
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
    *,
    model: str,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "finish_reason": finish_reason,
        "usage": dict(result.usage),
        "model": result.model or model,
        "provider": turn.conversation.provider,
        "step": step,
        "cache_prefix_hash": cache_prefix_hash,
        "citations": list(dict.fromkeys(CITATION_PATTERN.findall(result.text))),
    }
    reasoning = result.reasoning
    if reasoning:
        clipped = clip(reasoning, MAX_ASSISTANT_REASONING_CHARS)
        data["reasoning"] = clipped
        data["reasoning_chars"] = len(reasoning)
        data["reasoning_truncated"] = clipped != reasoning
    reasoning_tokens = result.usage.get("reasoning_tokens", 0)
    if isinstance(reasoning_tokens, int) and not isinstance(reasoning_tokens, bool):
        if reasoning_tokens > 0:
            data["reasoning_tokens"] = reasoning_tokens
    return data


def _normalize_finish(result: ChatResult) -> str | None:
    finish = (result.finish_reason or "").lower()
    if result.tool_calls:
        if finish in {"length", "content_filter"} or finish in ERROR_FINISH_REASONS:
            return None
        return "tool_calls"
    # A refusal is classified before the unusable branch so the escalation
    # ladder can react to it. An empty refusal has no text to show and is left
    # to the caller's unusable handling when no escalation is available.
    if finish == "refusal":
        return "refusal"
    if not result.text.strip():
        return None
    if finish in {"", "stop", "length"}:
        return finish or "stop"
    return None


def _fit_provider_context(
    context: ProviderContext,
    *,
    budget_tokens: int,
    chars_per_token: float,
    floor_tokens: int = 0,
) -> tuple[ProviderContext, _BudgetStats]:
    """Apply the message-level part of the overflow ladder to one request.

    Steps, in order and each re-estimated: drop page-context messages, clip
    tool-result bodies oldest-first at 8,000 → 2,000 → 500 characters while
    keeping the ``<tool_result>`` envelope, then truncate only the outbound copy
    of the current user message (head + tail with an explicit marker) and drop
    its inline attachments. If even that cannot fit, the request keeps the
    system prompt only. The stored transcript is never touched; this function
    only rewrites the provider projection.

    ``floor_tokens`` is the provider-reported prompt size for the current
    context segment. It is not content and cannot be reduced here, so a request
    whose floor already meets the budget runs every step: the ladder still
    removes all removable input instead of silently retrying an overshoot.
    """
    stats = _BudgetStats()

    def estimate(candidate: ProviderContext) -> int:
        return max(
            estimate_provider_context_tokens(
                candidate,
                chars_per_token=chars_per_token,
            ),
            floor_tokens,
        )

    current = context
    if estimate(current) <= budget_tokens:
        return current, stats

    # Step 2: page context is optional by construction and is dropped first.
    # The current user message is never a page snapshot even when its text
    # happens to look like one, so it is excluded from this pass.
    protected_index = _last_user_message_index(current.messages)
    kept: list[dict[str, Any]] = []
    for index, message in enumerate(current.messages):
        if index != protected_index and _is_page_context_message(message):
            stats.dropped_page_contexts += 1
            continue
        kept.append(message)
    if stats.dropped_page_contexts:
        current = replace(current, messages=kept)
        if estimate(current) <= budget_tokens:
            return current, stats

    # Step 3: clip tool-result bodies oldest-first, never the envelope.
    clipped_indices: set[int] = set()
    for cap in _TOOL_RESULT_BODY_CAPS:
        messages = list(current.messages)
        changed = False
        for index, message in enumerate(messages):
            if message.get("role") != "tool":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            limited = _clip_tool_result_content(content, cap)
            if limited != content:
                messages[index] = {**message, "content": limited}
                clipped_indices.add(index)
                changed = True
        if changed:
            stats.clipped_tool_results = len(clipped_indices)
            current = replace(current, messages=messages)
            if estimate(current) <= budget_tokens:
                return current, stats

    # Step 4: truncate the outbound copy of the current user message. Page
    # contexts are already gone, so the last user-role message is the turn's
    # own input, not a dropped snapshot.
    user_index = _last_user_message_index(current.messages)
    original_user_chars = 0
    if user_index is not None:
        user_message = current.messages[user_index]
        original_user_chars = _message_text_chars(user_message)
        # Reserve the message envelope and keep attachments out of the text
        # allowance: the text is fitted first, then attachments are dropped if
        # the request is still over budget.
        probe_content = _text_free_content(user_message.get("content"))
        probe_message = {**user_message, "content": probe_content}
        others = replace(
            current,
            messages=[
                *current.messages[:user_index],
                probe_message,
                *current.messages[user_index + 1 :],
            ],
        )
        allowance = max(
            0,
            math.floor((budget_tokens - estimate(others)) * chars_per_token) - 8,
        )
        truncated, truncated_chars = _truncate_user_text(user_message, allowance)
        if truncated_chars:
            messages = list(current.messages)
            messages[user_index] = truncated
            current = replace(current, messages=messages)
            stats.truncated_user_chars = truncated_chars
            if estimate(current) <= budget_tokens:
                return current, stats
        if estimate(current) > budget_tokens:
            dropped, attachment_count = _drop_user_attachments(current.messages[user_index])
            if attachment_count:
                messages = list(current.messages)
                messages[user_index] = dropped
                current = replace(current, messages=messages)
                stats.truncated_attachments = attachment_count
                if estimate(current) <= budget_tokens:
                    return current, stats

    # Step 5: the absolute last resort. A request that cannot fit even after the
    # user message was shortened keeps the system prompt only; the turn still
    # runs on the provider's own terms, never on a local context error.
    if estimate(current) > budget_tokens:
        stats.dropped_messages += len(current.messages)
        if user_index is not None and not stats.truncated_user_chars:
            stats.truncated_user_chars = original_user_chars
        current = replace(current, messages=[])
    return current, stats


def _is_page_context_message(message: Mapping[str, Any]) -> bool:
    content = message.get("content")
    return (
        message.get("role") == "user"
        and isinstance(content, str)
        and content.startswith("<page_context")
        and content.endswith("</page_context>")
    )


def _clip_tool_result_content(content: str, cap: int) -> str:
    """Clip a tool body while preserving the full ``<tool_result>`` envelope."""
    opening_end = content.find(">")
    closing_start = content.rfind("</tool_result>")
    if not content.startswith("<tool_result") or opening_end == -1 or closing_start == -1:
        return clip(content, cap)
    body = content[opening_end + 1 : closing_start]
    if len(body) <= cap:
        return content
    return (
        content[: opening_end + 1]
        + clip(body, cap)
        + content[closing_start:]
    )


def _last_user_message_index(messages: Sequence[Mapping[str, Any]]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            return index
    return None


def _text_free_content(content: object) -> object:
    """Return a message body with text and attachments removed for estimation."""
    if isinstance(content, str):
        return ""
    if not isinstance(content, list):
        return content
    return [
        part
        for part in content
        if not (
            isinstance(part, Mapping)
            and (
                isinstance(part.get("text"), str)
                or part.get("type") in _ATTACHMENT_PART_TYPES
            )
        )
    ]


def _message_text_chars(message: Mapping[str, Any]) -> int:
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    if not isinstance(content, list):
        return 0
    return sum(
        len(part["text"])
        for part in content
        if isinstance(part, Mapping) and isinstance(part.get("text"), str)
    )


def _truncate_user_text(
    message: Mapping[str, Any],
    allowance: int,
) -> tuple[dict[str, Any], int]:
    """Return a copy with the user text clipped, and the original character count.

    A string body gets the head/tail rule directly. A multimodal body clips its
    text parts in order and leaves attachments for the next ladder step.
    """
    content = message.get("content")
    if isinstance(content, str):
        if len(content) <= allowance:
            return dict(message), 0
        return {**message, "content": _head_tail_clip(content, allowance)}, len(content)
    if not isinstance(content, list):
        return dict(message), 0
    text_parts = [
        part
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    original_chars = sum(len(part["text"]) for part in text_parts)
    if original_chars <= allowance:
        return dict(message), 0
    updated: list[Any] = []
    remaining = allowance
    for part in content:
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            updated.append(part)
            continue
        if remaining <= 0:
            updated.append({**part, "text": ""})
            continue
        text = part["text"]
        if len(text) <= remaining:
            updated.append(part)
            remaining -= len(text)
            continue
        updated.append({**part, "text": _head_tail_clip(text, remaining)})
        remaining = 0
    return {**message, "content": updated}, original_chars


def _drop_user_attachments(
    message: Mapping[str, Any],
) -> tuple[dict[str, Any], int]:
    """Replace inline image/document parts with a short omitted marker."""
    content = message.get("content")
    if not isinstance(content, list):
        return dict(message), 0
    dropped = 0
    updated: list[Any] = []
    for part in content:
        kind = part.get("type") if isinstance(part, Mapping) else None
        if kind in _ATTACHMENT_PART_TYPES:
            dropped += 1
            updated.append({"type": "text", "text": _IMAGE_OMITTED_TEXT})
            continue
        updated.append(part)
    if not dropped:
        return dict(message), 0
    return {**message, "content": updated}, dropped


def _head_tail_clip(value: str, allowance: int) -> str:
    """Keep the opening instruction and the closing question of a long text."""
    if allowance <= 0:
        return ""
    if len(value) <= allowance:
        return value
    reserved = len(f"[… truncated {len(value)} characters …]")
    if allowance <= reserved:
        return value[:allowance]
    remaining = allowance - reserved
    head = int(remaining * _USER_MESSAGE_HEAD_RATIO)
    tail = remaining - head
    removed = max(0, len(value) - remaining)
    marker = f"[… truncated {removed} characters …]"
    return value[:head] + marker + (value[-tail:] if tail else "")


def _output_limit_text(max_output_tokens: int) -> str:
    """Explain a truncated turn without turning it into a failed run."""
    if max_output_tokens <= 0:
        return (
            "The response reached the provider's output limit before it could "
            "finish, so I could not complete that request. Please ask again for a "
            "smaller or simpler result, for example a chart with fewer points."
        )
    return (
        "The response reached this turn's output budget of "
        f"{max_output_tokens:,} tokens before it could finish, so I could not "
        "complete that request. Please ask again for a smaller or simpler result, "
        "for example a chart with fewer points."
    )


def _web_provider_name(value: str) -> str:
    """Keep only an available web provider name in the status block."""
    return value if value in {"tavily", "exa", "deepseek"} else "none"


def _plot_title_key(arguments: Mapping[str, Any]) -> str | None:
    """Return the case-folded title used by the duplicate-plot guard."""
    title = arguments.get("title")
    if not isinstance(title, str):
        return None
    normalized = title.strip().casefold()
    return normalized or None


def _is_rendered_plot(outcome: ToolOutcome) -> bool:
    """Return whether a plot outcome actually carries a renderable figure."""
    return outcome.error_code is None and isinstance(outcome.data.get("plot"), dict)


def _duplicate_plot_outcome(title: object) -> ToolOutcome:
    """Build the provider-visible duplicate notice without plot data."""
    safe_title = title if isinstance(title, str) else ""
    content = (
        f"<plot_already_rendered{attributes({'title': safe_title})}>"
        "A chart with this title is already visible in the chat. Do not call "
        "render_plot again; reply in text. If the user wants a different chart, "
        "wait for their next request."
        "</plot_already_rendered>"
    )
    return ToolOutcome(
        content=content,
        data={
            "tool": "render_plot",
            "status": "ok",
            "title": safe_title,
            "duplicate": True,
        },
    )


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
            "arguments": display_arguments(call.name, call.arguments),
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
