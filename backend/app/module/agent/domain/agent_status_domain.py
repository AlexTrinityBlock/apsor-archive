"""Provider-only agent status feedback for every agent model step.

The frozen ``pi.system`` entry carries the conversation prompt and tool snapshot.
Only a few runtime limits change per step, and a recoverable retry may add a
notice. Both are rendered into one trailing system message instead of rewriting
the frozen prefix. The block is always the final provider message, is never
persisted, and never returned to the UI, so the frozen prefix and its
prompt-cache lineage stay byte-identical.

Only limits the model can act on belong here. Attributes render in sorted key
order, so identical inputs produce byte-identical output.

The five optional context-budget values are the only mutable telemetry allowed:
they tell the model how much of the effective input budget this exact request
uses, how much remains, and how far away auto-compaction is. Identifiers,
content, paths, and usage counters stay out. The one tool-name exception is
``unavailable_tools``: the frozen prompt may describe web tools this account
cannot use right now, and the attribute tells the model they were withheld.
"""

from dataclasses import dataclass

from app.module.agent.domain.xml_domain import attributes


@dataclass(frozen=True)
class AgentStatus:
    """The model-actionable limits and optional retry notice for one provider call."""

    max_tool_result_chars: int
    max_page_context_chars: int
    max_expression_chars: int
    output_limit_tokens: int
    retry_notice: str | None = None
    # Estimated tokens of the complete ordered request including this block, the
    # effective input budget for the call, the tokens left before that budget,
    # the effective auto-compaction threshold, and the tokens left before it.
    context_used: int | None = None
    context_limit: int | None = None
    context_remaining: int | None = None
    compaction_at: int | None = None
    compaction_in: int | None = None
    # Catalog tools withheld from this request (sorted), e.g. web tools the
    # account has disabled or that have no configured provider.
    unavailable_tools: tuple[str, ...] = ()


def render_agent_status(status: AgentStatus) -> str:
    """Render the one trailing system message with the current runtime limits."""
    values: dict[str, int | str] = {
        "max_tool_result_chars": status.max_tool_result_chars,
        "max_page_context_chars": status.max_page_context_chars,
        "max_expression_chars": status.max_expression_chars,
    }
    if status.output_limit_tokens:
        values["output_limit_tokens"] = status.output_limit_tokens
    for key, value in (
        ("context_used", status.context_used),
        ("context_limit", status.context_limit),
        ("context_remaining", status.context_remaining),
        ("compaction_at", status.compaction_at),
        ("compaction_in", status.compaction_in),
    ):
        if value is not None:
            values[key] = value
    if status.unavailable_tools:
        values["unavailable_tools"] = ",".join(sorted(status.unavailable_tools))
    opening = "<agent_status" + attributes(values, sort_keys=True)
    if not status.retry_notice:
        return f"{opening} />"
    return "\n".join(
        [
            f"{opening}>",
            f"  {status.retry_notice}",
            "</agent_status>",
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


def render_invalid_arguments_notice() -> str:
    """Notice for two consecutive rejected tool-argument calls."""
    return (
        '<retry_notice reason="tool_arguments">The previous tool call had invalid '
        "arguments and was not executed. Do not resend the same arguments. If a "
        "chart is still needed, call render_plot once with a complete figure object; "
        "otherwise answer the user in text without a chart."
        "</retry_notice>"
    )


__all__ = [
    "AgentStatus",
    "render_agent_status",
    "render_context_overflow_notice",
    "render_invalid_arguments_notice",
    "render_output_limit_notice",
]
