"""Database-backed singleton for agent runtime limits."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
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
from app.shared.time import utcnow


class AgentConfigModel(Base):
    """One row (id=1) whose columns are the effective agent runtime limits.

    Provider and model are intentionally not stored here; they belong to the
    existing AI settings row so the model selection has a single source of truth.
    """

    __tablename__ = "agent_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "max_total_tokens BETWEEN 8000 AND 200000",
            name="max_total_tokens_range",
        ),
        CheckConstraint(
            "compaction_threshold_tokens BETWEEN 1000 AND 200000",
            name="compaction_threshold_tokens_range",
        ),
        CheckConstraint("max_steps BETWEEN 1 AND 32", name="max_steps_range"),
        CheckConstraint(
            "max_tool_calls_per_turn BETWEEN 1 AND 24",
            name="max_tool_calls_per_turn_range",
        ),
        CheckConstraint(
            "max_parallel_tools BETWEEN 1 AND 24",
            name="max_parallel_tools_range",
        ),
        CheckConstraint(
            "max_tool_result_chars BETWEEN 1000 AND 200000",
            name="max_tool_result_chars_range",
        ),
        CheckConstraint(
            "max_page_context_chars BETWEEN 500 AND 50000",
            name="max_page_context_chars_range",
        ),
        CheckConstraint(
            "max_compaction_summary_chars BETWEEN 1000 AND 20000",
            name="max_compaction_summary_chars_range",
        ),
        CheckConstraint(
            "max_compaction_last_user_chars BETWEEN 500 AND 10000",
            name="max_compaction_last_user_chars_range",
        ),
        CheckConstraint(
            "compaction_threshold_tokens < max_total_tokens",
            name="compaction_below_total",
        ),
        CheckConstraint(
            "max_parallel_tools <= max_tool_calls_per_turn",
            name="parallel_within_tool_calls",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    max_total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_TOTAL_TOKENS,
        server_default=text(str(MAX_TOTAL_TOKENS)),
    )
    compaction_threshold_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=COMPACTION_THRESHOLD_TOKENS,
        server_default=text(str(COMPACTION_THRESHOLD_TOKENS)),
    )
    max_steps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_STEPS,
        server_default=text(str(MAX_STEPS)),
    )
    max_tool_calls_per_turn: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_TOOL_CALLS_PER_TURN,
        server_default=text(str(MAX_TOOL_CALLS_PER_TURN)),
    )
    max_parallel_tools: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_PARALLEL_TOOLS,
        server_default=text(str(MAX_PARALLEL_TOOLS)),
    )
    max_tool_result_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_TOOL_RESULT_CHARS,
        server_default=text(str(MAX_TOOL_RESULT_CHARS)),
    )
    max_page_context_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_PAGE_CONTEXT_CHARS,
        server_default=text(str(MAX_PAGE_CONTEXT_CHARS)),
    )
    max_compaction_summary_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_COMPACTION_SUMMARY_CHARS,
        server_default=text(str(MAX_COMPACTION_SUMMARY_CHARS)),
    )
    max_compaction_last_user_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MAX_COMPACTION_LAST_USER_CHARS,
        server_default=text(str(MAX_COMPACTION_LAST_USER_CHARS)),
    )
    auto_compaction_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=AUTO_COMPACTION_ENABLED,
        server_default=text("true" if AUTO_COMPACTION_ENABLED else "false"),
    )
    parallel_tools_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=PARALLEL_TOOLS_ENABLED,
        server_default=text("true" if PARALLEL_TOOLS_ENABLED else "false"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )


__all__ = ["AgentConfigModel"]
