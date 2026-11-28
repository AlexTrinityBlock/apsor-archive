"""Application settings loaded from environment variables and local env files."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
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
            ".secrets/anthropic.env",
            "../.secrets/anthropic.env",
            ".secrets/openai.env",
            "../.secrets/openai.env",
            ".secrets/r2.env",
            "../.secrets/r2.env",
            ".secrets/s3.env",
            "../.secrets/s3.env",
            ".secrets/exa.env",
            "../.secrets/exa.env",
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

    # Storage. ``local`` keeps original bytes under ``data_dir``; ``r2`` writes
    # new originals to a private Cloudflare R2 bucket; ``s3`` writes to any
    # S3-compatible bucket (the bundled RustFS service, AWS S3, MinIO, ...).
    # ``rustfs`` is an alias for ``s3``. ``auto`` picks ``r2`` when R2 is fully
    # configured, else ``s3`` when S3 is, else ``local``; the production Compose
    # file uses it so an existing R2 deployment keeps working unchanged. Reads
    # always choose the backend persisted on the row, so a staged migration can
    # mix backends.
    storage_backend: Literal["auto", "local", "r2", "s3"] = "local"
    # ``R2_ACCOUNT_ENDPOINT``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``,
    # and ``R2_BUCKET`` are the names used by the local, gitignored
    # ``.secrets/r2.env``. Keep the unprefixed aliases so existing deployments
    # do not have to rewrite their secret file.
    r2_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APSOR_R2_ENDPOINT_URL",
            "R2_ENDPOINT_URL",
            "R2_ACCOUNT_ENDPOINT",
        ),
    )
    r2_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APSOR_R2_BUCKET",
            "R2_BUCKET",
        ),
    )
    r2_region: str = "auto"
    r2_access_key_id: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APSOR_R2_ACCESS_KEY_ID",
            "R2_ACCESS_KEY_ID",
        ),
    )
    r2_secret_access_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APSOR_R2_SECRET_ACCESS_KEY",
            "R2_SECRET_ACCESS_KEY",
        ),
    )
    # Optional key namespace inside the bucket. Database storage keys stay
    # unprefixed; the adapter applies this value transparently. Keep it
    # unchanged after a migration, otherwise existing objects become unreachable.
    r2_prefix: str = ""

    # Generic S3-compatible store. Credentials come from ``.secrets/s3.env``
    # (written by ``./start.sh setup``) and never from container environment
    # variables. ``s3_addressing_style`` is ``path`` for RustFS/MinIO and most
    # self-hosted servers; AWS S3 also accepts ``virtual``.
    # ``s3_create_bucket`` lets the first write create a missing bucket, which
    # the bundled RustFS service needs on a fresh volume.
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_prefix: str = ""
    s3_addressing_style: Literal["path", "virtual"] = "path"
    s3_create_bucket: bool = False

    max_upload_bytes: int = 10 * 1024 * 1024
    max_text_bytes: int = 2 * 1024 * 1024
    # Pasted chat screenshots are downscaled and re-encoded before storage.
    chat_attachment_max_bytes: int = 8 * 1024 * 1024
    max_chunks_per_file: int = 500
    vision_max_pages: int = 10
    pdf_text_threshold: int = 80

    chunk_target_chars: int = 4_000
    chunk_overlap_chars: int = 500
    # Seeds a fresh installation and remains the fallback when the
    # ``ingest_config`` row is absent. The database value applies to future
    # vision ingests.
    vision_description_language: str = "English"

    # Durable ingestion worker. The dedicated ``apsor-archive worker`` process
    # (``python -m app.worker`` / ``make worker``) owns ingestion. Setting
    # ``ingest_worker_enabled`` makes the API lifespan also run the worker loops
    # as an opt-in single-process development mode; it is off by default so
    # the API never extracts files unless asked to.
    #
    # The remaining values seed the database-backed singleton on a fresh
    # installation; the worker reads the database row and uses these only as a
    # fallback.
    ingest_worker_enabled: bool = False
    # The dedicated worker backfills WebP thumbnails for files that predate
    # them. Disable only to keep a constrained host from reading every original.
    thumbnail_backfill_enabled: bool = True
    # The dedicated worker embeds chunks that were stored without a vector
    # (provider out of credits, unreachable, rejected key, spent allowance) as
    # soon as the provider and the account allow it.
    embedding_backfill_enabled: bool = True
    ingest_poll_seconds: float = 1.0
    ingest_extract_workers: int = 2
    ingest_max_inflight_jobs: int = 2
    ingest_job_stale_seconds: int = 300
    ingest_job_max_attempts: int = 3
    ingest_embedding_batch_size: int = 16
    ingest_embedding_concurrency: int = 6
    ingest_embedding_max_attempts: int = 3
    ingest_embedding_retry_seconds: float = 0.25

    # RabbitMQ wake-up dispatch for durable ingestion. PostgreSQL
    # ``file_ingest_job`` remains the authoritative ledger; the broker only
    # reduces the latency between enqueue and a worker claim. When disabled, the
    # worker polls the database exactly as before.
    rabbitmq_enabled: bool = False
    rabbitmq_url: SecretStr | None = None
    rabbitmq_ingest_exchange: str = "apsor.ingest"
    rabbitmq_ingest_queue: str = "apsor.ingest.jobs"
    rabbitmq_ingest_retry_queue: str = "apsor.ingest.jobs.retry"
    rabbitmq_connect_timeout_seconds: float = 5.0
    # A publish must never hold up the upload response. The wake-up is
    # best-effort; the durable row is already queued for polling.
    rabbitmq_publish_timeout_seconds: float = 1.0
    rabbitmq_retry_ttl_ms: int = 30_000
    rabbitmq_max_dispatch_retries: int = 20

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
    # Small extraction/summary completions keep a tight cap. Agent turns can
    # legitimately emit large tool arguments (for example a long memory), so
    # they use a separate, larger output budget. Zero disables the chat cap:
    # the chat payload omits max_tokens and the provider applies its own limit.
    deepseek_max_tokens: int = 1800
    deepseek_chat_max_tokens: int = 20_000
    deepseek_temperature: float = 0.2

    # Anthropic Messages API. The key can live in ``.secrets/anthropic.env`` as
    # ``ANTHROPIC_API_KEY`` (or the prefixed name); a key stored on an active
    # provider row wins. ``anthropic_max_tokens`` is the shared background
    # text/JSON cap; agent chat uses ``chat_agent_max_output_tokens`` unless the
    # chat row sets its own ``max_output_tokens``.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "APSOR_ANTHROPIC_API_KEY"),
    )
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_timeout_seconds: float = 120.0
    anthropic_max_tokens: int = 2000
    anthropic_version: str = "2026-10-21"
    chat_agent_max_output_tokens: int = 64_000
    # Connection probes are interactive, so they use their own short timeout
    # instead of the regular chat timeout.
    chat_probe_timeout_seconds: float = 20.0

    # Tavily is the environment fallback for the two independent web
    # capabilities.  A database row always wins; when neither capability has an
    # active row, both resolve to TAVILY_API_KEY as specified by the plan.
    tavily_api_key: SecretStr | None = None
    tavily_base_url: str = "https://api.tavily.com"
    # Advanced extraction handles JS-heavy pages, tables, and embedded content
    # more reliably. It costs two credits per five successful extractions and
    # has a longer provider timeout.
    tavily_extract_depth: Literal["basic", "advanced"] = "advanced"
    # Exa is a separate search/fetch provider. The key can live in
    # ``.secrets/exa.env`` as ``EXA_API_KEY`` or in the encrypted provider row.
    exa_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("EXA_API_KEY", "APSOR_EXA_API_KEY"),
    )
    exa_base_url: str = "https://api.exa.ai"
    web_search_timeout_seconds: float = 25.0
    # The provider's advanced extraction may use up to 30 seconds; keep the
    # HTTP client above that so it does not time out while Tavily is finishing.
    web_fetch_timeout_seconds: float = 45.0
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

    @field_validator("storage_backend", mode="before")
    @classmethod
    def _normalize_storage_backend(cls, value: object) -> object:
        """Accept ``rustfs`` (and any letter case) as a name for ``s3``."""
        if isinstance(value, str):
            candidate = value.strip().lower()
            return "s3" if candidate == "rustfs" else candidate
        return value

    @property
    def resolved_storage_backend(self) -> Literal["local", "r2", "s3"]:
        """Concrete backend for new writes after resolving ``auto``."""
        if self.storage_backend != "auto":
            return self.storage_backend
        if self.r2_configured:
            return "r2"
        if self.s3_configured:
            return "s3"
        return "local"

    @property
    def s3_configured(self) -> bool:
        """Whether every non-secret and secret S3 setting is present."""
        return not self.s3_missing_settings

    @property
    def s3_missing_settings(self) -> list[str]:
        """Return missing setting names only; never include values."""
        missing: list[str] = []
        if not (self.s3_endpoint_url or "").strip():
            missing.append("s3_endpoint_url")
        if not (self.s3_bucket or "").strip():
            missing.append("s3_bucket")
        if not self._has_secret(self.s3_access_key_id):
            missing.append("s3_access_key_id")
        if not self._has_secret(self.s3_secret_access_key):
            missing.append("s3_secret_access_key")
        return missing

    @property
    def r2_configured(self) -> bool:
        """Whether every non-secret and secret R2 setting is present."""
        return not self.r2_missing_settings

    @property
    def r2_missing_settings(self) -> list[str]:
        """Return missing setting names only; never include values."""
        missing: list[str] = []
        if not (self.r2_endpoint_url or "").strip():
            missing.append("r2_endpoint_url")
        if not (self.r2_bucket or "").strip():
            missing.append("r2_bucket")
        if not self._has_secret(self.r2_access_key_id):
            missing.append("r2_access_key_id")
        if not self._has_secret(self.r2_secret_access_key):
            missing.append("r2_secret_access_key")
        return missing

    @staticmethod
    def _has_secret(value: SecretStr | None) -> bool:
        return value is not None and bool(value.get_secret_value().strip())


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
