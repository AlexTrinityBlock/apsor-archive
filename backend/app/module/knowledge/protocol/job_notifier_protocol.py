"""Wake-up dispatch port for durable ingestion jobs.

PostgreSQL ``file_ingest_job`` remains the authoritative ledger. A notification
only names a job that the worker still claims and re-reads from the database, so
a lost, duplicated, or stale message can never become a second source of truth.
"""

from typing import Protocol


class JobNotifierProtocol(Protocol):
    """Signal the ingestion worker that one durable job is ready."""

    async def notify(self, job_id: int) -> None:
        """Publish one wake-up hint for a queued job.

        Implementations must never raise: enqueue stays successful when the
        wake-up path is unavailable, and polling remains the fallback.
        """
        ...

    async def close(self) -> None:
        """Release the underlying connection, if any."""
        ...


class NullJobNotifier:
    """No-op notifier used when broker dispatch is disabled."""

    async def notify(self, job_id: int) -> None:
        del job_id

    async def close(self) -> None:
        return None


__all__ = ["JobNotifierProtocol", "NullJobNotifier"]
