"""SQLAlchemy persistence and lease operations for ingestion jobs.

Two access modes exist:

* an owner-scoped repository (``user_id`` set) used by request handlers and by
  per-job worker work; every read and write carries ``user_id``;
* a maintenance repository (``user_id=None``) used only with
  ``maintenance_session`` to claim and recover jobs across owners.
"""

from datetime import datetime
from typing import TypeVar

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.ingest_job_model import (
    INGEST_ACTIVE_STATUSES,
    INGEST_PROCESSING_STATUSES,
    INGEST_STATUS_FAILED,
    INGEST_STATUS_PARSING,
    INGEST_STATUS_QUEUED,
    FileIngestJobModel,
)
from app.shared.time import utcnow

_Row = TypeVar("_Row")


class IngestJobRepository:
    """Queries over the durable job queue; no parsing decisions live here."""

    def __init__(self, session: AsyncSession, user_id: int | None = None) -> None:
        self.session = session
        self.user_id = user_id

    def _scoped(self, statement: Select[_Row]) -> Select[_Row]:
        """Apply the owner predicate when this repository is not maintenance."""
        if self.user_id is None:
            return statement
        return statement.where(FileIngestJobModel.user_id == self.user_id)

    async def add(self, job: FileIngestJobModel) -> FileIngestJobModel:
        if self.user_id is not None:
            job.user_id = self.user_id
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: int) -> FileIngestJobModel | None:
        statement = self._scoped(
            select(FileIngestJobModel).where(FileIngestJobModel.id == job_id)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_recent(self, *, limit: int, offset: int) -> list[FileIngestJobModel]:
        statement = self._scoped(
            select(FileIngestJobModel).order_by(
                FileIngestJobModel.created_at.desc(),
                FileIngestJobModel.id.desc(),
            )
        ).offset(offset).limit(limit)
        return list((await self.session.execute(statement)).scalars().all())

    async def count(self) -> int:
        statement = self._scoped(select(func.count(FileIngestJobModel.id)))
        return int((await self.session.execute(statement)).scalar_one())

    async def _claim(
        self,
        statement: Select[FileIngestJobModel],
        *,
        now: datetime,
    ) -> FileIngestJobModel | None:
        job = (
            await self.session.execute(statement.with_for_update(skip_locked=True))
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = INGEST_STATUS_PARSING
        job.stage = "Reading and extracting text"
        job.progress_pct = 5
        job.attempts += 1
        job.started_at = now
        job.finished_at = None
        job.error_code = None
        job.error_detail = None
        job.updated_at = now
        await self.session.flush()
        return job

    async def claim_next(self) -> FileIngestJobModel | None:
        """Lease the oldest queued job with ``FOR UPDATE SKIP LOCKED``."""
        statement = self._scoped(
            select(FileIngestJobModel)
            .where(FileIngestJobModel.status == INGEST_STATUS_QUEUED)
            .order_by(FileIngestJobModel.created_at, FileIngestJobModel.id)
            .limit(1)
        )
        return await self._claim(statement, now=utcnow())

    async def claim(self, job_id: int) -> FileIngestJobModel | None:
        """Lease one specific queued job, used by tests and the ``--once`` mode."""
        statement = self._scoped(
            select(FileIngestJobModel)
            .where(
                FileIngestJobModel.id == job_id,
                FileIngestJobModel.status == INGEST_STATUS_QUEUED,
            )
            .limit(1)
        )
        return await self._claim(statement, now=utcnow())

    async def list_stale(self, *, stale_before: datetime) -> list[FileIngestJobModel]:
        """Lock and return processing jobs whose heartbeat has expired."""
        statement = self._scoped(
            select(FileIngestJobModel)
            .where(
                FileIngestJobModel.status.in_(INGEST_PROCESSING_STATUSES),
                FileIngestJobModel.updated_at < stale_before,
            )
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def clear_file_id(self, job_id: int) -> None:
        """Detach a staged file without refreshing the job heartbeat.

        Startup recovery must clear the foreign key before deleting the staged
        file (``ON DELETE CASCADE`` would otherwise remove the job). The
        heartbeat must stay stale so the requeue query still sees the row, so
        ``updated_at`` is assigned to itself to suppress the column's
        ``onupdate`` default.
        """
        statement = (
            update(FileIngestJobModel)
            .where(FileIngestJobModel.id == job_id)
            .values(file_id=None, updated_at=FileIngestJobModel.updated_at)
        )
        if self.user_id is not None:
            statement = statement.where(FileIngestJobModel.user_id == self.user_id)
        await self.session.execute(statement)

    async def requeue_stale(
        self,
        *,
        stale_before: datetime,
        max_attempts: int,
    ) -> tuple[int, list[tuple[str, str | None]]]:
        """Recover jobs left mid-flight by a crashed process.

        A job whose last heartbeat is older than ``stale_before`` is returned to
        the queue. When the attempt budget is exhausted it becomes a terminal
        failure instead of being retried forever. Returns the recovered count
        and ``(storage_key, storage_backend)`` pairs for terminal payloads that
        can be removed.
        """
        statement = self._scoped(
            select(FileIngestJobModel)
            .where(
                FileIngestJobModel.status.in_(INGEST_PROCESSING_STATUSES),
                FileIngestJobModel.updated_at < stale_before,
            )
            .with_for_update(skip_locked=True)
        )
        jobs = list((await self.session.execute(statement)).scalars().all())
        now = utcnow()
        terminal_payloads: list[tuple[str, str | None]] = []
        for job in jobs:
            # The claim that started this attempt already incremented the
            # counter. Recovery must not consume a second attempt just because
            # the worker died before it could finish.
            job.updated_at = now
            if job.attempts >= max_attempts:
                job.status = INGEST_STATUS_FAILED
                job.stage = "Interrupted too many times"
                job.error_code = "ingest_worker_lost"
                job.error_detail = (
                    "The worker stopped while this job was in progress and the "
                    "attempt limit was reached."
                )
                job.finished_at = now
                if job.storage_key is not None and job.file_id is None:
                    terminal_payloads.append((job.storage_key, job.storage_backend))
            else:
                job.status = INGEST_STATUS_QUEUED
                job.stage = "Requeued after an interrupted worker"
                job.started_at = None
        await self.session.flush()
        return len(jobs), terminal_payloads

    @staticmethod
    def is_active(status: str) -> bool:
        return status in INGEST_ACTIVE_STATUSES
