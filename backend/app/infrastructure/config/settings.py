"""Application settings loaded from environment variables and local env files."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPOSITORY_ROOT = BACKEND_ROOT.parent
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Runtime configuration for the Apsor Archive API."""

    model_config = SettingsConfigDict(
        env_prefix="APSOR_",
        env_file=(
            ".env",
            "../.env",
            ".secrets/deepseek.env",
            "../.secrets/deepseek.env",
            ".secrets/openai.env",
            "../.secrets/openai.env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Apsor Archive"
    version: str = "0.1.0"
    environment: str = "local"
    debug: bool = False

    database_url: str = "postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive"
    data_dir: Path = BACKEND_ROOT / "data"
    static_dir: Path = REPOSITORY_ROOT / "frontend" / "dist"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )

    cache_url: str = "redis://127.0.0.1:56379/0"
    cache_ttl_seconds: int = 120

    max_upload_bytes: int = 10 * 1024 * 1024
    max_text_bytes: int = 2 * 1024 * 1024
    max_chunks_per_file: int = 500
    vision_max_pages: int = 10
    pdf_text_threshold: int = 80

    chunk_target_chars: int = 4_000
    chunk_overlap_chars: int = 500

    # Durable ingestion worker. The lifespan task is a convenience for local
    # single-process development; production can run ``python -m app.worker``
    # (or ``apsor-archive worker``) as a dedicated service.
    #
    # These values seed the database-backed singleton on a fresh installation;
    # the worker reads the database row and uses these only as a fallback.
    ingest_worker_enabled: bool = True
    ingest_poll_seconds: float = 1.0
    ingest_extract_workers: int = 2
    ingest_max_inflight_jobs: int = 2
    ingest_job_stale_seconds: int = 300
    ingest_job_max_attempts: int = 3
    ingest_embedding_batch_size: int = 16
    ingest_embedding_concurrency: int = 6
    ingest_embedding_max_attempts: int = 3
    ingest_embedding_retry_seconds: float = 0.25

    search_candidate_limit: int = 200
    search_vector_scan_limit: int = 20_000
    timeline_max_day_range: int = 366

    embedding_provider: Literal["hashing", "openai", "none"] = "hashing"
    embedding_dimension: int = 384
    embedding_model: str = "apsor-hash-384"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_timeout_seconds: float = 30.0

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: float = 60.0
    deepseek_max_tokens: int = 1800
    deepseek_temperature: float = 0.2

    # Tavily is the environment fallback for the two independent web
    # capabilities.  A database row always wins; when neither capability has an
    # active row, both resolve to TAVILY_API_KEY as specified by the plan.
    tavily_api_key: SecretStr | None = None
    tavily_base_url: str = "https://api.tavily.com"
    web_search_timeout_seconds: float = 25.0
    web_fetch_timeout_seconds: float = 30.0
    web_search_cache_ttl_seconds: int = 900
    web_fetch_cache_ttl_seconds: int = 3600
    web_fetch_max_chars: int = 20_000

    # Master key for encrypting API keys stored in the database. When unset, a
    # 0600 key file is created under the data directory.
    secret_key: SecretStr | None = None

    ai_summary_enabled: bool = True
    auto_summary_threshold: int = 10
    summary_min_memories: int = 2

    run_migrations: bool = True
    timezone: str = "Asia/Taipei"
    gzip_minimum_size: int = 500

    # Cookie session for the single owner account.
    session_ttl_hours: int = 24 * 30
    cookie_name: str = "apsor_session"
    cookie_secure: bool = False
    login_attempt_limit: int = 10
    login_window_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    A mounted secret file can be present but unreadable (for example, a 0600
    bind mount read by a non-root container user). In that case the API still
    starts with AI disabled and logs one clear warning, instead of failing to
    boot with an opaque traceback.
    """
    try:
        return Settings()
    except OSError as exc:
        logger.warning("Could not read an environment file; continuing without it: %s", exc)
        return Settings(_env_file=None)
