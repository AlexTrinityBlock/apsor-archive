"""Provider-only agent status feedback for every agent model step.

The frozen ``pi.system`` entry carries the conversation prompt and tool snapshot.
Only a few runtime limits change per step, and a recoverable retry may add a
notice. Both are rendered into one trailing system message instead of rewriting
the frozen prefix. The block is always the final provider message, is never
persisted, and never returned to the UI, so the frozen prefix and its
prompt-cache lineage stay byte-identical.

Only limits the model can act on belong here. Attributes render in sorted key
order, so identical inputs produce byte-identical output.
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


def render_agent_status(status: AgentStatus) -> str:
    """Render the one trailing system message with the current runtime limits."""
    opening = (
        "<agent_status"
        + attributes(
            {
                "max_tool_result_chars": status.max_tool_result_chars,
                "max_page_context_chars": status.max_page_context_chars,
                "max_expression_chars": status.max_expression_chars,
                "output_limit_tokens": status.output_limit_tokens,
            },
            sort_keys=True,
        )
    )
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


__all__ = [
    "AgentStatus",
    "render_agent_status",
    "render_context_overflow_notice",
    "render_output_limit_notice",
]
