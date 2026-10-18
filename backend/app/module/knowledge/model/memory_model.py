"""Linear memory records with explicit supersession history."""

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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow

MEMORY_ACTIVE = "active"
MEMORY_DEPRECATED = "deprecated"
MEMORY_STATUSES = (MEMORY_ACTIVE, MEMORY_DEPRECATED)

MEMORY_SOURCE_MANUAL = "manual"
MEMORY_SOURCE_AI = "ai"
MEMORY_SOURCE_IMPORT = "import"
MEMORY_SOURCES = (MEMORY_SOURCE_MANUAL, MEMORY_SOURCE_AI, MEMORY_SOURCE_IMPORT)


class MemoryModel(Base):
    """One memory on the timeline.

    A deprecated memory keeps its row and its content. Only its search chunk is
    marked non-current; ``read_memory`` can still walk the whole chain.
    """

    __tablename__ = "memory"
    __table_args__ = (
        Index(
            "ix_memory_time_active",
            "memory_time",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_memory_superseded_by", "superseded_by_id"),
        Index("ix_memory_supersedes_ids", "supersedes_ids", postgresql_using="gin"),
        CheckConstraint("status IN ('active', 'deprecated')", name="status_valid"),
        CheckConstraint("source IN ('manual', 'ai', 'import')", name="source_valid"),
        CheckConstraint(
            "status = 'active' OR superseded_by_id IS NOT NULL",
            name="deprecated_has_successor",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MEMORY_ACTIVE)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("memory.id", ondelete="SET NULL"), nullable=True
    )
    supersedes_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, default=list, server_default=text("'{}'::bigint[]")
    )
    memory_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=MEMORY_SOURCE_MANUAL)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
