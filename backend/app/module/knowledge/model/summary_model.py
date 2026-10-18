"""Periodic summaries over a window of the memory timeline."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow


class MemorySummaryModel(Base):
    """A narrative summary of a set of memories."""

    __tablename__ = "memory_summary"
    __table_args__ = (
        Index("ix_memory_summary_period_end", "period_end"),
        Index("ix_memory_summary_source_ids", "source_memory_ids", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    memory_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_memory_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'::bigint[]")
    )
    themes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    generator: Mapped[str] = mapped_column(Text, nullable=False, default="extractive")
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
