"""Provider-only self-awareness block for every agent model step.

The frozen ``pi.system`` entry carries the conversation prompt and tool snapshot.
Runtime facts change per step (remaining steps, tool calls, context, usage), so
they are rendered into one trailing system message instead of rewriting the
frozen prefix. The block is never persisted and never returned to the UI.

Only operational metadata belongs here: identity, provider/model, frozen
versions, conversation/run ids, counts, the frozen tool names, capability
availability, limits, and the run's accumulated usage. User content, archive
content, the account profile, paths, and credentials must never enter this block.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.module.agent.domain.xml_domain import attributes, xml_text

RUNTIME_LIMITS_INSTRUCTION = (
    "These are trusted runtime limits. Plan within them. Keep generated or random "
    "chart data to 50-200 points. A <retry_notice> means a previous attempt hit a "
    "limit; do not repeat it, produce a smaller result."
)

AGENT_SELF_INSTRUCTION = (
    "These are your own runtime facts, not user content or archive evidence. Plan "
    "within them; do not restate them unless the user asks about your limits."
)


@dataclass(frozen=True)
class RuntimeLimits:
    """The model-actionable limits and effective behaviors for one provider call."""

    context_window_tokens: int
    estimated_context_tokens: int
    remaining_context_tokens: int
    compaction_threshold_tokens: int
    output_limit_tokens: int
    step: int
    max_steps: int
    remaining_steps: int
    tool_calls_used: int
    max_tool_calls_per_turn: int
    remaining_tool_calls: int
    max_parallel_tools: int
    max_tool_result_chars: int
    max_page_context_chars: int
    max_plot_traces: int
    max_plot_points: int
    max_plot_bytes: int
    max_expression_chars: int
    parallel_tools_enabled: bool
    auto_compaction_enabled: bool
    save_memory_requires_approval: bool
    retry_notice: str | None = None


@dataclass(frozen=True)
class AgentSelf:
    """Safe operational facts about the agent run for one provider call."""

    provider: str
    active_provider: str
    model: str
    prompt_version: str
    tools_version: str
    conversation_id: int
    run_id: int
    approval_resume: bool
    new_page_context: bool
    active_context_entries: int
    tool_names: tuple[str, ...]
    web_search: str
    web_fetch: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int | None
    limits: RuntimeLimits


def render_runtime_limits(
    limits: RuntimeLimits,
    *,
    retry_notice: str | None = None,
) -> str:
    """Render the nested runtime-limits element.

    ``retry_notice`` overrides the dataclass field so a caller can render the
    same limits with a notice after a recoverable limit failure.
    """
    values = {
        "context_window_tokens": limits.context_window_tokens,
        "estimated_context_tokens": limits.estimated_context_tokens,
        "remaining_context_tokens": limits.remaining_context_tokens,
        "compaction_threshold_tokens": limits.compaction_threshold_tokens,
        "output_limit_tokens": limits.output_limit_tokens,
        "step": limits.step,
        "max_steps": limits.max_steps,
        "remaining_steps": limits.remaining_steps,
        "tool_calls_used": limits.tool_calls_used,
        "max_tool_calls_per_turn": limits.max_tool_calls_per_turn,
        "remaining_tool_calls": limits.remaining_tool_calls,
        "max_parallel_tools": limits.max_parallel_tools,
        "max_tool_result_chars": limits.max_tool_result_chars,
        "max_page_context_chars": limits.max_page_context_chars,
        "max_plot_traces": limits.max_plot_traces,
        "max_plot_points": limits.max_plot_points,
        "max_plot_bytes": limits.max_plot_bytes,
        "max_expression_chars": limits.max_expression_chars,
        "parallel_tools_enabled": _bool(limits.parallel_tools_enabled),
        "auto_compaction_enabled": _bool(limits.auto_compaction_enabled),
        "save_memory_requires_approval": _bool(
            limits.save_memory_requires_approval
        ),
    }
    body = [RUNTIME_LIMITS_INSTRUCTION]
    notice = retry_notice if retry_notice is not None else limits.retry_notice
    if notice:
        body.append(notice)
    return (
        f"<runtime_limits{attributes(values)}>\n"
        + "\n".join(body)
        + "\n</runtime_limits>"
    )


def render_agent_self(agent_self: AgentSelf) -> str:
    """Render the one trailing system message with nested runtime facts."""
    limits = agent_self.limits
    identity = _single_line(
        "<identity",
        {
            "name": "Apsor Archive Agent",
            "role": "persistent archive research agent",
            "scope": "private archive of the signed-in account",
            "transcript": "append_only",
        },
        close=" />",
    )
    runtime = _single_line(
        "<runtime",
        {
            "provider": agent_self.provider,
            "active_provider": agent_self.active_provider,
            "model": agent_self.model,
            "prompt_version": agent_self.prompt_version,
            "tools_version": agent_self.tools_version,
        },
        close=" />",
    )
    session = _single_line(
        "<session",
        {
            "conversation_id": agent_self.conversation_id,
            "run_id": agent_self.run_id,
            "step": limits.step,
            "max_steps": limits.max_steps,
            "remaining_steps": limits.remaining_steps,
            # This is an approval-resume flag, not a generic "continued" flag.
            "approval_resume": _bool(agent_self.approval_resume),
            # Explicitly a new snapshot for this turn; older page context may
            # still exist in the active context.
            "new_page_context": (
                "attached" if agent_self.new_page_context else "none"
            ),
            "active_context_entries": agent_self.active_context_entries,
        },
        close=" />",
    )
    capability_values = {
        "tool_count": len(agent_self.tool_names),
        "web_search": agent_self.web_search,
        "web_fetch": agent_self.web_fetch,
    }
    capabilities = (
        f"<capabilities{attributes(capability_values)}>"
        f"{xml_text(', '.join(agent_self.tool_names))}</capabilities>"
    )
    limits_block = "\n".join(
        f"  {line}" for line in render_runtime_limits(limits).splitlines()
    )
    usage_values: dict[str, object] = {
        "prompt_tokens": agent_self.prompt_tokens,
        "completion_tokens": agent_self.completion_tokens,
        "total_tokens": agent_self.total_tokens,
    }
    if agent_self.cached_tokens is not None:
        usage_values["cached_tokens"] = agent_self.cached_tokens
    usage = _single_line("<usage", usage_values, close=" />")
    return "\n".join(
        [
            "<agent_self>",
            f"  {identity}",
            f"  {runtime}",
            f"  {session}",
            f"  {capabilities}",
            limits_block,
            f"  {usage}",
            f"  <instruction>{xml_text(AGENT_SELF_INSTRUCTION)}</instruction>",
            "</agent_self>",
        ]
    )


def render_output_limit_notice() -> str:
    """Notice for a completion truncated at the output-token cap."""
    return (
        '<retry_notice reason="output_limit">The previous completion reached the '
        "output token limit and was truncated before any tool ran. Produce a smaller "
        "result now: for chart data use 50-100 points and keep the figure compact."
        "</retry_notice>"
    )


def render_context_overflow_notice() -> str:
    """Notice for a request that exceeded the context window."""
    return (
        '<retry_notice reason="context_window">The previous request exceeded the '
        "context window and the context was compacted. Continue from the compacted "
        "context; do not repeat work that was already completed."
        "</retry_notice>"
    )


def _single_line(
    name: str,
    values: Mapping[str, object],
    *,
    close: str,
) -> str:
    return f"{name}{attributes(values)}{close}"


def _bool(value: bool) -> str:
    return "true" if value else "false"


__all__ = [
    "AGENT_SELF_INSTRUCTION",
    "RUNTIME_LIMITS_INSTRUCTION",
    "AgentSelf",
    "RuntimeLimits",
    "render_agent_self",
    "render_context_overflow_notice",
    "render_output_limit_notice",
    "render_runtime_limits",
]
