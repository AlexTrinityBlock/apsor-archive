"""Schemas for health and statistics."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StatsSchema(BaseModel):
    """Library-wide counts shown on the home and settings screens."""

    model_config = ConfigDict(frozen=True)

    file_count: int
    chunk_count: int
    memory_count: int
    active_memory_count: int
    summary_count: int
    storage_bytes: int
    oldest_memory_time: datetime | None
    newest_memory_time: datetime | None


class HealthSchema(BaseModel):
    """Cheap liveness information without secrets."""

    model_config = ConfigDict(frozen=True)

    status: str
    version: str
    database: str
    cache: str
    ai: str
    embedding_provider: str
    # Explicit web capability state: provider name plus a configured flag.
    web_search_provider: str
    web_search_configured: bool
    web_fetch_provider: str
    web_fetch_configured: bool


class EmbeddingBackfillStatusSchema(BaseModel):
    """Root-only view of chunks still waiting for an embedding.

    ``pending_chunks`` counts rows whose text is indexed (keyword search works)
    but whose vector is still missing; the worker fills them in automatically.
    ``worker_state`` is what the dedicated worker last published: ``running``,
    ``idle``, ``paused`` (provider failure; resumes at ``resume_at``),
    ``disabled`` (no embedding provider), or ``unknown`` (no report yet).
    Only counts and stable codes appear here, never chunk text.
    """

    model_config = ConfigDict(frozen=True)

    pending_chunks: int
    pending_accounts: int
    abandoned_chunks: int
    worker_state: str
    resume_at: datetime | None
    last_error_code: str | None
    allowance_blocked_accounts: int
    updated_at: datetime | None
