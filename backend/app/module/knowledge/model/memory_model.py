"""Linear memory records with explicit supersession history."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
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

    A deprecated memory keeps its row and its content. It is deprecated either
    because a successor replaced it (``superseded_by_id``) or because the keeper
    retired it directly (``deprecated_at`` with no successor). Only its search
    chunk is marked non-current; ``read_memory`` can still walk the whole chain.
    """

    __tablename__ = "memory"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_memory_id_user_id"),
        ForeignKeyConstraint(
            ["superseded_by_id", "user_id"],
            ["memory.id", "memory.user_id"],
            name="fk_memory_superseded_by_user",
            ondelete="SET NULL (superseded_by_id)",
        ),
        Index(
            "ix_memory_time_active",
            "memory_time",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_memory_user_id_time_active",
            "user_id",
            "memory_time",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_memory_superseded_by", "superseded_by_id"),
        Index("ix_memory_supersedes_ids", "supersedes_ids", postgresql_using="gin"),
        CheckConstraint("status IN ('active', 'deprecated')", name="status_valid"),
        CheckConstraint("source IN ('manual', 'ai', 'import')", name="source_valid"),
        CheckConstraint(
            "status = 'active' OR superseded_by_id IS NOT NULL OR deprecated_at IS NOT NULL",
            name="deprecated_has_provenance",
        ),
        CheckConstraint(
            "deprecated_reason IS NULL OR char_length(deprecated_reason) <= 500",
            name="deprecated_reason_length",
        ),
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_length"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_memory_user_id_app_user",
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MEMORY_ACTIVE)
    superseded_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
