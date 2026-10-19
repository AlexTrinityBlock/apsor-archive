"""Immutable settings snapshot for the ingestion worker loop.

The database stores the mutable source of truth. The worker is expected to load
one snapshot per loop or job and pass it through as this frozen value object, so
a settings change made while a job is running cannot alter that job halfway.
Environment values are only the seed for a fresh installation and the fallback
used when no database row exists.
"""

from dataclasses import dataclass

INGEST_POLL_SECONDS = 1.0
INGEST_EXTRACT_WORKERS = 2
INGEST_MAX_INFLIGHT_JOBS = 2
INGEST_EMBEDDING_CONCURRENCY = 6
INGEST_CHUNK_TARGET_CHARS = 4_000
INGEST_CHUNK_OVERLAP_CHARS = 500


@dataclass(frozen=True)
class IngestRuntimeConfig:
    """One validated, immutable snapshot of the ingestion worker settings."""

    poll_seconds: float = INGEST_POLL_SECONDS
    extract_workers: int = INGEST_EXTRACT_WORKERS
    max_inflight_jobs: int = INGEST_MAX_INFLIGHT_JOBS
    embedding_concurrency: int = INGEST_EMBEDDING_CONCURRENCY
    chunk_target_chars: int = INGEST_CHUNK_TARGET_CHARS
    chunk_overlap_chars: int = INGEST_CHUNK_OVERLAP_CHARS

    def __post_init__(self) -> None:
        """Reject values the database constraints also reject."""
        if (
            not isinstance(self.poll_seconds, (int, float))
            or isinstance(self.poll_seconds, bool)
            or self.poll_seconds < 0.25
            or self.poll_seconds > 30
        ):
            raise ValueError("poll_seconds must be between 0.25 and 30.")
        ranges = (
            ("extract_workers", self.extract_workers, 1, 8),
            ("max_inflight_jobs", self.max_inflight_jobs, 1, 4),
            ("embedding_concurrency", self.embedding_concurrency, 1, 32),
            ("chunk_target_chars", self.chunk_target_chars, 1_000, 20_000),
            ("chunk_overlap_chars", self.chunk_overlap_chars, 0, 5_000),
        )
        for name, value, minimum, maximum in ranges:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer.")
            if value < minimum or value > maximum:
                raise ValueError(
                    f"{name} must be between {minimum} and {maximum}."
                )
        if self.chunk_overlap_chars >= self.chunk_target_chars:
            raise ValueError(
                "chunk_overlap_chars must be less than chunk_target_chars."
            )


__all__ = [
    "INGEST_CHUNK_OVERLAP_CHARS",
    "INGEST_CHUNK_TARGET_CHARS",
    "INGEST_EMBEDDING_CONCURRENCY",
    "INGEST_EXTRACT_WORKERS",
    "INGEST_MAX_INFLIGHT_JOBS",
    "INGEST_POLL_SECONDS",
    "IngestRuntimeConfig",
]
