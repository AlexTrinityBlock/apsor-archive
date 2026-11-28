"""ORM models for generated life stories and their durable jobs.

Both tables are private (``{table}_owner``) and visible to root under the
companion admin scope (``{table}_companion_admin``). A generated story is a
per-account lore item (``fragment_key`` ``g-<id>``) that may surface like any
other memory; ``source_refs`` keeps memory/file ids and counts, never content.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class CompanionStoryJobModel(Base):
    """One durable life-story job (queued → running → terminal)."""

    __tablename__ = "companion_story_job"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_companion_story_job_id_user_id"),
        UniqueConstraint(
            "user_id",
            "trigger_key",
            name="uq_companion_story_job_user_id_trigger_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    companion_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(128), nullable=False)
    replaces_story_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanionGeneratedStoryModel(Base):
    """One life story written for one account and companion."""

    __tablename__ = "companion_generated_story"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "user_id"],
            ["companion_story_job.id", "companion_story_job.user_id"],
            name="fk_companion_generated_story_job_user",
            ondelete="SET NULL (job_id)",
        ),
        UniqueConstraint("user_id", "job_id", name="uq_companion_generated_story_user_id_job_id"),
        UniqueConstraint(
            "user_id",
            "companion_ref",
            "fragment_key",
            name="uq_companion_generated_story_user_id_ref_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    companion_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    fragment_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    themes: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    source_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_config_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sql_text("now()"),
    )


__all__ = ["CompanionGeneratedStoryModel", "CompanionStoryJobModel"]
