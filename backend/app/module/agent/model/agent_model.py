"""Immutable Pi-shaped transcript tables for the archive agent."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow

AGENT_COMMIT_SEQUENCE = Sequence("agent_commit_seq")


class AgentConversationModel(Base):
    """Transcript scope plus editable metadata; prompt/tools live in entries."""

    __tablename__ = "agent_conversation"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_agent_conversation_id_user_id"),
        UniqueConstraint(
            "user_id",
            "provider_session_id",
            name="uq_agent_conversation_provider_session_id",
        ),
        ForeignKeyConstraint(
            ["parent_conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name="fk_agent_conversation_parent_user",
            ondelete="SET NULL (parent_conversation_id)",
        ),
        ForeignKeyConstraint(
            ["fork_at_entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name="fk_agent_conversation_fork_entry_user",
            ondelete="SET NULL (fork_at_entry_id)",
            use_alter=True,
        ),
        CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        Index("ix_agent_conversation_last_entry_at", "last_entry_at"),
        Index("ix_agent_conversation_status", "status"),
        Index(
            "ix_agent_conversation_user_id_last_entry_at",
            "user_id",
            "last_entry_at",
        ),
        Index("ix_agent_conversation_user_id_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_agent_conversation_user_id_app_user",
        ),
        nullable=False,
    )
    parent_conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fork_at_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_session_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentEntryModel(Base):
    """One immutable transcript event.

    ``model`` is exactly what the provider sees; ``data`` is UI/diagnostics and is
    never sent to the provider. Corrections are new entries with ``head_entry_id``
    or ``edits``, never updates to this row.
    """

    __tablename__ = "agent_entry"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_agent_entry_id_user_id"),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name="fk_agent_entry_conversation_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["head_entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name="fk_agent_entry_head_user",
            ondelete="SET NULL (head_entry_id)",
        ),
        ForeignKeyConstraint(
            ["by_run_id", "user_id"],
            ["agent_run.id", "agent_run.user_id"],
            name="fk_agent_entry_run_user",
            ondelete="SET NULL (by_run_id)",
            use_alter=True,
        ),
        CheckConstraint(
            "kind IN ('pi.user', 'pi.assistant', 'pi.tool-result', "
            "'pi.page-context', 'pi.system', 'pi.reset', 'pi.compaction', "
            "'ui.notice')",
            name="kind_valid",
        ),
        CheckConstraint(
            "kind NOT IN ('pi.user', 'pi.assistant', 'pi.tool-result', "
            "'pi.page-context', 'pi.system') OR model IS NOT NULL",
            name="model_required",
        ),
        CheckConstraint(
            "kind <> 'pi.tool-result' OR model->0->>'tool_call_id' IS NOT NULL",
            name="tool_result_call_id",
        ),
        CheckConstraint(
            "edits IS NULL OR jsonb_typeof(edits) = 'array'",
            name="edits_array",
        ),
        Index("ix_agent_entry_conversation_id", "conversation_id", "id"),
        Index("ix_agent_entry_conversation_commit", "conversation_id", "commit_seq"),
        Index(
            "ix_agent_entry_user_id_conversation_id",
            "user_id",
            "conversation_id",
            "id",
        ),
        Index(
            "ix_agent_entry_head",
            "conversation_id",
            desc("id"),
            postgresql_where=text("head_entry_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_agent_entry_user_id_app_user",
        ),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commit_seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=AGENT_COMMIT_SEQUENCE.next_value(),
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    data: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    head_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    edits: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    by_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AgentApprovalModel(Base):
    """One pending human decision for a confirmation-required tool call.

    The row is durable operational state, not transcript content. It stores the
    validated arguments, a safe UI preview, and the loop snapshot needed to
    resume the same run after an explicit approve or reject. The transcript
    remains append-only: the assistant tool call is already persisted, and the
    real tool result is appended only when the approval is resolved.
    """

    __tablename__ = "agent_approval"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name="fk_agent_approval_conversation_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["agent_run.id", "agent_run.user_id"],
            name="fk_agent_approval_run_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["resolved_by_entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name="fk_agent_approval_resolved_entry_user",
            ondelete="SET NULL (resolved_by_entry_id)",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="status_valid",
        ),
        Index(
            "ix_agent_approval_conversation_status",
            "conversation_id",
            "status",
            "id",
        ),
        Index(
            "ix_agent_approval_user_id_conversation_status",
            "user_id",
            "conversation_id",
            "status",
        ),
        Index("ix_agent_approval_run_status", "run_id", "status"),
        Index(
            "uq_agent_approval_pending_call",
            "run_id",
            "tool_call_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_agent_approval_user_id_app_user",
        ),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resume_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolved_by_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AgentRunModel(Base):
    """Durable operational state for one user submission."""

    __tablename__ = "agent_run"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_agent_run_id_user_id"),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["agent_conversation.id", "agent_conversation.user_id"],
            name="fk_agent_run_conversation_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["last_entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name="fk_agent_run_last_entry_user",
            ondelete="SET NULL (last_entry_id)",
        ),
        ForeignKeyConstraint(
            ["user_entry_id", "user_id"],
            ["agent_entry.id", "agent_entry.user_id"],
            name="fk_agent_run_user_entry_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('running', 'waiting', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0 "
            "AND cached_tokens >= 0 AND api_calls >= 0",
            name="usage_non_negative",
        ),
        Index("ix_agent_run_conversation_id", "conversation_id", "id"),
        Index("ix_agent_run_conversation_status", "conversation_id", "status"),
        Index(
            "ix_agent_run_user_id_conversation_id",
            "user_id",
            "conversation_id",
            "id",
        ),
        Index(
            "ix_agent_run_user_id_conversation_status",
            "user_id",
            "conversation_id",
            "status",
        ),
        Index(
            "uq_agent_run_request",
            "conversation_id",
            "request_id",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
        ),
        Index(
            "uq_agent_run_running",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_agent_run_user_id_app_user",
        ),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_entry_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="running",
        server_default="running",
    )
    abort_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    last_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    prompt_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cached_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    api_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
