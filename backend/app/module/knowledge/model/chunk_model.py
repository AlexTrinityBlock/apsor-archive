"""Unified chunk table shared by files, memories, and summaries."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow

SOURCE_FILE = "file"
SOURCE_MEMORY = "memory"
SOURCE_SUMMARY = "summary"
# A past conversation message. ``source_id`` is the immutable ``agent_entry``
# id, and the content is one 256-character raw window. Conversation history
# shares this flat table deliberately: it gets the same owner-scoped index,
# BM25/vector recall, and embedding reindex as every other knowledge source.
SOURCE_HISTORY = "history"
SOURCE_KINDS = (SOURCE_FILE, SOURCE_MEMORY, SOURCE_SUMMARY, SOURCE_HISTORY)


class ChunkModel(Base):
    """One searchable slice of a file, memory, or summary.

    The source is polymorphic on purpose: one inverted index, one vector table,
    and one result contract for every knowledge source. Source metadata stays in
    its owning table and is joined by ``(source_kind, source_id)``.
    """

    __tablename__ = "chunk"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_chunk_id_user_id"),
        Index(
            "uq_chunk_current_source_ordinal",
            "user_id",
            "source_kind",
            "source_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_chunk_source", "source_kind", "source_id"),
        Index("ix_chunk_current", "is_current"),
        Index("ix_chunk_user_id_source", "user_id", "source_kind", "source_id"),
        Index("ix_chunk_user_id_current", "user_id", "is_current"),
        # The embedding backfill scans only rows still waiting for a vector.
        Index(
            "ix_chunk_pending_embedding",
            "user_id",
            "id",
            postgresql_where=text("embedding IS NULL"),
        ),
        CheckConstraint(
            "source_kind IN ('file', 'memory', 'summary', 'history')",
            name="source_kind_valid",
        ),
        CheckConstraint("chunk_index >= 1", name="chunk_index_positive"),
        CheckConstraint("char_count >= 0", name="char_count_non_negative"),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        CheckConstraint(
            "embedding_failures >= 0",
            name="embedding_failures_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_chunk_user_id_app_user",
        ),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # ``none_as_null`` stores a missing vector as SQL NULL, never JSON ``null``,
    # so "pending" has one meaning and the partial index below can see it.
    embedding: Mapped[list[float] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Per-chunk embedding failures (HTTP 400/413/422 on this text). Systemic
    # failures (billing, quota, auth, outages) never count here, so every
    # pending row is retried once the provider recovers. A NULL ``embedding``
    # with ``embedding_failures`` below the backfill limit is still pending.
    embedding_failures: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_current: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def embedding_as_list(self) -> list[float] | None:
        """Return a typed embedding list from JSONB storage."""
        raw: Any = self.embedding
        if raw is None:
            return None
        return [float(value) for value in raw]
