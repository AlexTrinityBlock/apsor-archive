"""SQLAlchemy persistence and lease operations for ingestion jobs."""

from datetime import datetime

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


class IngestJobRepository:
    """Queries over the durable job queue; no parsing decisions live here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: FileIngestJobModel) -> FileIngestJobModel:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: int) -> FileIngestJobModel | None:
        return await self.session.get(FileIngestJobModel, job_id)

    async def list_recent(self, *, limit: int, offset: int) -> list[FileIngestJobModel]:
        statement = (
            select(FileIngestJobModel)
            .order_by(FileIngestJobModel.created_at.desc(), FileIngestJobModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count(self) -> int:
        return int(
            (await self.session.execute(select(func.count(FileIngestJobModel.id)))).scalar_one()
        )

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
        statement = (
            select(FileIngestJobModel)
            .where(FileIngestJobModel.status == INGEST_STATUS_QUEUED)
            .order_by(FileIngestJobModel.created_at, FileIngestJobModel.id)
            .limit(1)
        )
        return await self._claim(statement, now=utcnow())

    async def claim(self, job_id: int) -> FileIngestJobModel | None:
        """Lease one specific queued job, used by tests and the ``--once`` mode."""
        statement = (
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
        statement = (
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
        file (``ON DELETE CASCADE`` would otherwise remove the job). A normal
        ORM assignment would also bump ``updated_at`` through ``onupdate`` and
        make the row invisible to the stale-job query that runs immediately
        afterwards, so use an explicit Core update here.
        """
        await self.session.execute(
            update(FileIngestJobModel).where(FileIngestJobModel.id == job_id).values(file_id=None)
        )

    async def requeue_stale(
        self,
        *,
        stale_before: datetime,
        max_attempts: int,
    ) -> tuple[int, list[str]]:
        """Recover jobs left mid-flight by a crashed process.

        A job whose last heartbeat is older than ``stale_before`` is returned to
        the queue. When the attempt budget is exhausted it becomes a terminal
        failure instead of being retried forever. Returns the recovered count
        and the storage keys of terminal jobs whose payloads can be removed.
        """
        statement = (
            select(FileIngestJobModel)
            .where(
                FileIngestJobModel.status.in_(INGEST_PROCESSING_STATUSES),
                FileIngestJobModel.updated_at < stale_before,
            )
            .with_for_update(skip_locked=True)
        )
        jobs = list((await self.session.execute(statement)).scalars().all())
        now = utcnow()
        terminal_payloads: list[str] = []
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
                    terminal_payloads.append(job.storage_key)
            else:
                job.status = INGEST_STATUS_QUEUED
                job.stage = "Requeued after an interrupted worker"
                job.started_at = None
        await self.session.flush()
        return len(jobs), terminal_payloads

    @staticmethod
    def is_active(status: str) -> bool:
        return status in INGEST_ACTIVE_STATUSES
