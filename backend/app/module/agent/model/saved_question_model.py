"""Saved questions, their latest answer, and the conversation that produced it."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class SavedQuestionModel(Base):
    """One owner-visible question in the saved Q&A library.

    ``answer`` is nullable so a question can be captured before it is asked.
    ``citations`` stores the citation tokens extracted from the final assistant
    entry (for example ``["file:12#1"]``). The last ask outcome is persisted in
    ``run_status`` / ``error_code`` / ``error_detail`` so a failed attempt stays
    visible instead of deleting or silently resetting the saved question.
    """

    __tablename__ = "saved_question"
    __table_args__ = (
        CheckConstraint(
            "char_length(question) BETWEEN 1 AND 32000",
            name="question_length",
        ),
        CheckConstraint("jsonb_typeof(citations) = 'array'", name="citations_array"),
        CheckConstraint(
            "run_status IS NULL OR run_status IN "
            "('running', 'waiting', 'completed', 'failed', 'cancelled')",
            name="run_status_valid",
        ),
        Index("ix_saved_question_conversation_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_conversation.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    last_asked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = ["SavedQuestionModel"]
