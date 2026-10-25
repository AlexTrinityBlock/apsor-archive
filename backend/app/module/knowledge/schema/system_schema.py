"""Schemas for health, statistics, and demo seeding."""

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


class DemoSeedSchema(BaseModel):
    """What the demo seed created."""

    model_config = ConfigDict(frozen=True)

    files_created: int
    memories_created: int
    summaries_created: int
