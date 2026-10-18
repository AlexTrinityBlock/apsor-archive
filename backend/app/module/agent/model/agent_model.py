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
    Identity,
    Index,
    Sequence,
    String,
    Text,
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
        CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        Index("ix_agent_conversation_last_entry_at", "last_entry_at"),
        Index("ix_agent_conversation_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    parent_conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_conversation.id", ondelete="SET NULL"),
        nullable=True,
    )
    fork_at_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "agent_entry.id",
            use_alter=True,
            name="fk_agent_conversation_fork_at_entry_id_agent_entry",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_session_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=False,
        unique=True,
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
        CheckConstraint(
            "kind IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system', "
            "'pi.reset', 'pi.compaction', 'ui.notice')",
            name="kind_valid",
        ),
        CheckConstraint(
            "kind NOT IN ('pi.user', 'pi.assistant', 'pi.tool-result', 'pi.system') "
            "OR model IS NOT NULL",
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
            "ix_agent_entry_head",
            "conversation_id",
            desc("id"),
            postgresql_where=text("head_entry_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=AGENT_COMMIT_SEQUENCE.next_value(),
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    data: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    head_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    edits: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    by_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "agent_run.id",
            use_alter=True,
            name="fk_agent_entry_by_run_id_agent_run",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AgentRunModel(Base):
    """Durable operational state for one user submission."""

    __tablename__ = "agent_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'waiting', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        Index("ix_agent_run_conversation_id", "conversation_id", "id"),
        Index("ix_agent_run_conversation_status", "conversation_id", "status"),
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
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_entry_id: Mapped[int] = mapped_column(
        ForeignKey("agent_entry.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    last_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
