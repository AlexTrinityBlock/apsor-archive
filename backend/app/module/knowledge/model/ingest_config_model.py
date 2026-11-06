"""Database-backed singleton for ingestion worker runtime settings."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.module.knowledge.domain.ingest_config_domain import (
    INGEST_CHUNK_OVERLAP_CHARS,
    INGEST_CHUNK_TARGET_CHARS,
    INGEST_EMBEDDING_CONCURRENCY,
    INGEST_EXTRACT_WORKERS,
    INGEST_MAX_INFLIGHT_JOBS,
    INGEST_POLL_SECONDS,
    VISION_DESCRIPTION_LANGUAGE,
)
from app.shared.time import utcnow


class IngestConfigModel(Base):
    """One row (id=1) whose columns are the effective ingestion settings.

    The worker reads this table into ``IngestRuntimeConfig``; the values here are
    separate from the environment variables used by the synchronous file
    ingestion path, so changing the worker knobs never silently reconfigures an
    in-flight request. The two nullable vision prompt columns store the current
    templates; ``NULL`` means the built-in default.
    """

    __tablename__ = "ingest_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "poll_seconds BETWEEN 0.25 AND 30",
            name="poll_seconds_range",
        ),
        CheckConstraint(
            "extract_workers BETWEEN 1 AND 8",
            name="extract_workers_range",
        ),
        CheckConstraint(
            "max_inflight_jobs BETWEEN 1 AND 4",
            name="max_inflight_jobs_range",
        ),
        CheckConstraint(
            "embedding_concurrency BETWEEN 1 AND 32",
            name="embedding_concurrency_range",
        ),
        CheckConstraint(
            "chunk_target_chars BETWEEN 1000 AND 20000",
            name="chunk_target_chars_range",
        ),
        CheckConstraint(
            "chunk_overlap_chars BETWEEN 0 AND 5000",
            name="chunk_overlap_chars_range",
        ),
        CheckConstraint(
            "chunk_overlap_chars < chunk_target_chars",
            name="overlap_below_target",
        ),
        CheckConstraint(
            "char_length(btrim(vision_description_language)) BETWEEN 1 AND 80",
            name="vision_description_language_length",
        ),
        CheckConstraint(
            "vision_image_prompt IS NULL "
            "OR char_length(btrim(vision_image_prompt)) BETWEEN 1 AND 32000",
            name="vision_image_prompt_length",
        ),
        CheckConstraint(
            "vision_document_prompt IS NULL "
            "OR char_length(btrim(vision_document_prompt)) BETWEEN 1 AND 32000",
            name="vision_document_prompt_length",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    poll_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=INGEST_POLL_SECONDS,
        server_default=text(str(INGEST_POLL_SECONDS)),
    )
    extract_workers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INGEST_EXTRACT_WORKERS,
        server_default=text(str(INGEST_EXTRACT_WORKERS)),
    )
    max_inflight_jobs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INGEST_MAX_INFLIGHT_JOBS,
        server_default=text(str(INGEST_MAX_INFLIGHT_JOBS)),
    )
    embedding_concurrency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INGEST_EMBEDDING_CONCURRENCY,
        server_default=text(str(INGEST_EMBEDDING_CONCURRENCY)),
    )
    chunk_target_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INGEST_CHUNK_TARGET_CHARS,
        server_default=text(str(INGEST_CHUNK_TARGET_CHARS)),
    )
    chunk_overlap_chars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INGEST_CHUNK_OVERLAP_CHARS,
        server_default=text(str(INGEST_CHUNK_OVERLAP_CHARS)),
    )
    vision_description_language: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=VISION_DESCRIPTION_LANGUAGE,
        server_default=text(f"'{VISION_DESCRIPTION_LANGUAGE}'"),
    )
    vision_image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    vision_document_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )


__all__ = ["IngestConfigModel"]
