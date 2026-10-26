"""Durable ingestion jobs for uploads and direct text documents.

The job table is the queue, the progress ledger, and the crash-recovery record
for one worker pipeline. Large payloads are never stored here: uploads keep
their original bytes in file storage, and direct text is written to a small
temporary storage key that the worker deletes after the job finishes.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow

INGEST_SOURCE_UPLOAD = "upload"
INGEST_SOURCE_TEXT = "text"
INGEST_SOURCES = (INGEST_SOURCE_UPLOAD, INGEST_SOURCE_TEXT)

INGEST_STATUS_QUEUED = "queued"
INGEST_STATUS_PARSING = "parsing"
INGEST_STATUS_CHUNKING = "chunking"
INGEST_STATUS_EMBEDDING = "embedding"
INGEST_STATUS_SUMMARIZING = "summarizing"
INGEST_STATUS_READY = "ready"
INGEST_STATUS_FAILED = "failed"
INGEST_STATUSES = (
    INGEST_STATUS_QUEUED,
    INGEST_STATUS_PARSING,
    INGEST_STATUS_CHUNKING,
    INGEST_STATUS_EMBEDDING,
    INGEST_STATUS_SUMMARIZING,
    INGEST_STATUS_READY,
    INGEST_STATUS_FAILED,
)
INGEST_ACTIVE_STATUSES = (
    INGEST_STATUS_QUEUED,
    INGEST_STATUS_PARSING,
    INGEST_STATUS_CHUNKING,
    INGEST_STATUS_EMBEDDING,
    INGEST_STATUS_SUMMARIZING,
)
INGEST_PROCESSING_STATUSES = (
    INGEST_STATUS_PARSING,
    INGEST_STATUS_CHUNKING,
    INGEST_STATUS_EMBEDDING,
    INGEST_STATUS_SUMMARIZING,
)


class FileIngestJobModel(Base):
    """One durable ingestion attempt for a file path.

    ``status`` is the lifecycle state, while ``stage`` is the human-readable
    sentence shown next to the progress bar. ``attempts`` is incremented when a
    worker claims the row, so startup recovery and manual retries stay bounded.
    """

    __tablename__ = "file_ingest_job"
    __table_args__ = (
        ForeignKeyConstraint(
            ["file_id", "user_id"],
            ["file.id", "file.user_id"],
            name="fk_file_ingest_job_file_user",
            ondelete="CASCADE",
        ),
        # Only one active job may target a path per user. Ready and failed jobs
        # are historical and must not block a fresh upload.
        Index(
            "uq_file_ingest_job_active_path",
            "user_id",
            "path",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'parsing', 'chunking', 'embedding', 'summarizing')"
            ),
        ),
        Index(
            "uq_file_ingest_job_file_id",
            "file_id",
            unique=True,
            postgresql_where=text("file_id IS NOT NULL"),
        ),
        Index("ix_file_ingest_job_status_created", "status", "created_at"),
        Index(
            "ix_file_ingest_job_user_id_status_created",
            "user_id",
            "status",
            "created_at",
        ),
        Index("ix_file_ingest_job_updated_at", "updated_at"),
        CheckConstraint(
            "storage_backend IN ('local', 'r2')",
            name="storage_backend_valid",
        ),
        CheckConstraint(
            "(storage_key IS NULL) = (storage_backend IS NULL)",
            name="storage_backend_key_pair",
        ),
        CheckConstraint(
            "source_kind IN ('upload', 'text')",
            name="source_kind_valid",
        ),
        CheckConstraint(
            "status IN ('queued', 'parsing', 'chunking', 'embedding', "
            "'summarizing', 'ready', 'failed')",
            name="status_valid",
        ),
        CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="progress_pct_range",
        ),
        CheckConstraint(
            "chunks_total IS NULL OR chunks_total >= 0",
            name="chunks_total_non_negative",
        ),
        CheckConstraint(
            "chunks_embedded IS NULL OR chunks_embedded >= 0",
            name="chunks_embedded_non_negative",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_file_ingest_job_user_id_app_user",
        ),
        nullable=False,
    )
    file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=INGEST_STATUS_QUEUED,
        server_default=INGEST_STATUS_QUEUED,
    )
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_pct: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    chunks_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks_embedded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        onupdate=utcnow,
        server_default=text("now()"),
    )
