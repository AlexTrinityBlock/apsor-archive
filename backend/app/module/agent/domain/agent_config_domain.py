"""Immutable runtime limits for the agent turn loop.

The database stores the mutable source of truth. A request loads it once into
this frozen value object and passes that snapshot to ``AgentService``, so an
active SSE run never observes a settings change made by another request.

Provider and model selection are deliberately absent: they remain in the
database-backed AI runtime settings (``/api/v1/settings/ai``) so there is only
one source of truth for which model answers.
"""

from dataclasses import dataclass

from app.module.agent.domain.agent_domain import (
    AUTO_COMPACTION_ENABLED,
    COMPACTION_THRESHOLD_TOKENS,
    MAX_COMPACTION_LAST_USER_CHARS,
    MAX_COMPACTION_SUMMARY_CHARS,
    MAX_PAGE_CONTEXT_CHARS,
    MAX_PARALLEL_TOOLS,
    MAX_STEPS,
    MAX_TOOL_CALLS_PER_TURN,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOTAL_TOKENS,
    PARALLEL_TOOLS_ENABLED,
)


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """One validated, immutable snapshot of the agent runtime limits."""

    max_total_tokens: int = MAX_TOTAL_TOKENS
    compaction_threshold_tokens: int = COMPACTION_THRESHOLD_TOKENS
    max_steps: int = MAX_STEPS
    max_tool_calls_per_turn: int = MAX_TOOL_CALLS_PER_TURN
    max_parallel_tools: int = MAX_PARALLEL_TOOLS
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS
    max_page_context_chars: int = MAX_PAGE_CONTEXT_CHARS
    max_compaction_summary_chars: int = MAX_COMPACTION_SUMMARY_CHARS
    max_compaction_last_user_chars: int = MAX_COMPACTION_LAST_USER_CHARS
    auto_compaction_enabled: bool = AUTO_COMPACTION_ENABLED
    parallel_tools_enabled: bool = PARALLEL_TOOLS_ENABLED

    def __post_init__(self) -> None:
        """Reject values the database constraints also reject."""
        ranges = (
            ("max_total_tokens", self.max_total_tokens, 8_000, 200_000),
            (
                "compaction_threshold_tokens",
                self.compaction_threshold_tokens,
                1_000,
                200_000,
            ),
            ("max_steps", self.max_steps, 1, 32),
            (
                "max_tool_calls_per_turn",
                self.max_tool_calls_per_turn,
                1,
                24,
            ),
            ("max_parallel_tools", self.max_parallel_tools, 1, 24),
            ("max_tool_result_chars", self.max_tool_result_chars, 1_000, 200_000),
            ("max_page_context_chars", self.max_page_context_chars, 500, 50_000),
            (
                "max_compaction_summary_chars",
                self.max_compaction_summary_chars,
                1_000,
                20_000,
            ),
            (
                "max_compaction_last_user_chars",
                self.max_compaction_last_user_chars,
                500,
                10_000,
            ),
        )
        for name, value, minimum, maximum in ranges:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer.")
            if value < minimum or value > maximum:
                raise ValueError(
                    f"{name} must be between {minimum} and {maximum}."
                )
        if self.compaction_threshold_tokens >= self.max_total_tokens:
            raise ValueError(
                "compaction_threshold_tokens must be less than max_total_tokens."
            )
        if self.max_parallel_tools > self.max_tool_calls_per_turn:
            raise ValueError(
                "max_parallel_tools must not exceed max_tool_calls_per_turn."
            )


__all__ = ["AgentRuntimeConfig"]
