"""Durable ingestion jobs: enqueue, progress tracking, and worker pipeline.

The HTTP layer only validates the payload, stores the original bytes, and
inserts a job row. A bounded worker claims queued rows with
``SELECT ... FOR UPDATE SKIP LOCKED`` and advances them through parsing,
chunking, embedding, and publishing.

Ownership and RLS are part of the queue contract:

* requests enqueue and inspect jobs through an owner-scoped repository;
* the worker claims and recovers jobs across owners with
  ``maintenance_session``;
* every file, chunk, n-gram, and checkpoint after a claim runs inside
  ``user_session(job.user_id, "user")``, and checkpoints use
  ``commit_and_reapply`` so the transaction-local RLS context survives.

Two deployment shapes share this service:

* the FastAPI lifespan starts one in-process worker for local development;
* ``python -m app.worker`` / ``apsor-archive worker`` runs a dedicated process.

Both modes are single-loop workers; multiple API replicas should disable the
lifespan task and run dedicated workers instead. Parsing and chunking run on a
bounded ``ThreadPoolExecutor`` while a semaphore caps in-flight jobs per worker.
"""

import asyncio
import logging
import mimetypes
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.session import (
    ROLE_USER,
    commit_and_reapply,
    maintenance_session,
    user_session,
)
from app.infrastructure.files.storage_errors import (
    StorageError,
    StorageObjectMissingError,
    StorageUnavailableError,
)
from app.module.knowledge.domain.ingest_config_domain import IngestRuntimeConfig
from app.module.knowledge.domain.ingest_progress_domain import (
    PHASE_CHUNKING,
    PHASE_PARSING,
    ProgressTracker,
)
from app.module.knowledge.domain.path_domain import extension
from app.module.knowledge.domain.vision_prompt_domain import vision_mode_for_extension
from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    EmbeddingProviderError,
    EmbeddingUsageLimitExceededError,
    EmptyContentError,
    FileContentUnavailableError,
    FileStorageUnavailableError,
    FileTooLargeError,
    FileVersionConflictError,
    IngestJobConflictError,
    IngestJobNotFoundError,
    IngestJobNotRetryableError,
    IngestSourceStaleError,
    InvalidPathError,
    KnowledgeError,
    SpreadsheetArchiveTooLargeError,
    TooManyChunksError,
    TreePathConflictError,
    UnsupportedFileTypeError,
    VisionExtractionError,
)
from app.module.knowledge.model.ingest_job_model import (
    INGEST_PROCESSING_STATUSES,
    INGEST_SOURCE_REINGEST,
    INGEST_SOURCE_TEXT,
    INGEST_SOURCE_UPLOAD,
    INGEST_STATUS_CHUNKING,
    INGEST_STATUS_EMBEDDING,
    INGEST_STATUS_FAILED,
    INGEST_STATUS_PARSING,
    INGEST_STATUS_QUEUED,
    INGEST_STATUS_READY,
    INGEST_STATUS_SUMMARIZING,
    FileIngestJobModel,
)
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.ingest_progress_protocol import IngestProgressProtocol
from app.module.knowledge.protocol.job_notifier_protocol import (
    JobNotifierProtocol,
    NullJobNotifier,
)
from app.module.knowledge.protocol.progress_bus_protocol import ProgressBusProtocol
from app.module.knowledge.repository.ingest_job_repository import IngestJobRepository
from app.module.knowledge.schema.file_schema import (
    IngestJobListSchema,
    IngestJobSchema,
    IngestJobStatus,
    IngestProgressEventSchema,
    IngestSourceKind,
)
from app.module.knowledge.service.file_service import (
    ALLOWED_EXTENSIONS,
    FileService,
    ReingestSource,
)
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

# A broker outage must never stall extraction or embedding; a dropped progress
# event only means one missed UI update.
PROGRESS_PUBLISH_TIMEOUT_SECONDS = 1.0

_ERROR_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (EmptyContentError, "empty_content"),
    (TooManyChunksError, "too_many_chunks"),
    (UnsupportedFileTypeError, "unsupported_file_type"),
    (FileTooLargeError, "file_too_large"),
    (SpreadsheetArchiveTooLargeError, "spreadsheet_archive_too_large"),
    (TreePathConflictError, "tree_path_conflict"),
    (InvalidPathError, "invalid_path"),
    (VisionExtractionError, "vision_extraction_failed"),
    (AiNotConfiguredError, "ai_not_configured"),
    (AiProviderError, "ai_provider_error"),
    (EmbeddingProviderError, "embedding_provider_error"),
    (EmbeddingUsageLimitExceededError, "embedding_usage_limit_exceeded"),
    (FileStorageUnavailableError, "storage_unavailable"),
    (IngestSourceStaleError, "ingest_source_stale"),
    (FileContentUnavailableError, "file_content_unavailable"),
    (FileVersionConflictError, "file_version_conflict"),
    (FileNotFoundError, "ingest_payload_missing"),
    (KnowledgeError, "knowledge_error"),
)


def ingest_error_code(exc: BaseException) -> str:
    """Map an ingestion exception to a stable, readable error code."""
    for exc_type, code in _ERROR_CODES:
        if isinstance(exc, exc_type):
            return code
    return "ingest_failed"


FileServiceFactory = Callable[
    [
        AsyncSession,
        int,
        IngestRuntimeConfig,
        asyncio.Semaphore,
        asyncio.Semaphore,
        ProgressTracker | None,
    ],
    Awaitable[FileService],
]

ClaimedJob = tuple[int, int]

NotifiedJobOutcome = Literal["processed", "terminal", "retry", "missing"]


@dataclass(frozen=True)
class _WorkerRuntime:
    """One immutable settings snapshot plus the gates it owns."""

    config: IngestRuntimeConfig
    extract_semaphore: asyncio.Semaphore
    embedding_semaphore: asyncio.Semaphore
    job_slots: asyncio.Semaphore


def _to_schema(job: FileIngestJobModel) -> IngestJobSchema:
    return IngestJobSchema(
        id=job.id,
        file_id=job.file_id,
        source_file_id=job.source_file_id,
        source_kind=cast(IngestSourceKind, job.source_kind),
        path=job.path,
        file_name=job.file_name,
        mime_type=job.mime_type,
        size_bytes=job.size_bytes,
        occurred_at=job.occurred_at,
        status=cast(IngestJobStatus, job.status),
        stage=job.stage,
        progress_pct=job.progress_pct,
        stage_done=job.stage_done,
        stage_total=job.stage_total,
        stage_unit=job.stage_unit,
        chunks_total=job.chunks_total,
        chunks_embedded=job.chunks_embedded,
        error_code=job.error_code,
        error_detail=job.error_detail,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


class IngestJobService:
    """Request-scoped enqueue, lookup, and retry operations for one owner."""

    def __init__(
        self,
        *,
        user_id: int,
        repository: IngestJobRepository,
        file_service: FileService,
        max_attempts: int,
        notifier: JobNotifierProtocol | None = None,
    ) -> None:
        self.user_id = user_id
        self.repository = repository
        self.file_service = file_service
        self.max_attempts = max(1, max_attempts)
        self.notifier: JobNotifierProtocol = notifier or NullJobNotifier()

    async def _notify(self, job_id: int) -> None:
        """Wake a worker without ever failing the successful enqueue.

        The notifier adapter already swallows broker failures; this guard keeps
        the same guarantee for injected fakes and future implementations.
        """
        try:
            await self.notifier.notify(job_id)
        except Exception as exc:
            logger.warning(
                "Could not dispatch ingestion job %d to the wake-up queue (%s); "
                "database polling remains the fallback",
                job_id,
                type(exc).__name__,
            )

    async def _discard_storage(self, storage_key: str, backend: str | None) -> None:
        try:
            await self.file_service.storage.delete(storage_key, backend=backend)
        except Exception:
            logger.warning("Could not delete rejected ingestion payload %s", storage_key)

    async def _store_payload(self, storage_key: str, data: bytes, backend: str) -> None:
        """Store a queued payload, translating storage failures into a 503."""
        try:
            await self.file_service.storage.save(storage_key, data, backend=backend)
        except (StorageObjectMissingError, StorageUnavailableError, StorageError, OSError) as exc:
            raise FileStorageUnavailableError() from exc

    async def enqueue_upload(
        self,
        *,
        path: str,
        data: bytes,
        content_type: str | None,
        occurred_at: datetime | None,
    ) -> IngestJobSchema:
        """Store the original bytes and queue an upload for background ingest."""
        normalized = self.file_service.normalize_path(path)
        suffix = extension(normalized)
        if suffix not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(suffix)
        if len(data) > self.file_service.max_upload_bytes:
            raise FileTooLargeError(len(data), self.file_service.max_upload_bytes)
        mime_type = (
            content_type or mimetypes.guess_type(normalized)[0] or "application/octet-stream"
        )
        storage_key = self.file_service.new_storage_key(self.user_id, suffix)
        storage_backend = self.file_service.storage_backend
        await self._store_payload(storage_key, data, storage_backend)
        job = FileIngestJobModel(
            user_id=self.user_id,
            source_kind=INGEST_SOURCE_UPLOAD,
            path=normalized,
            storage_key=storage_key,
            storage_backend=storage_backend,
            mime_type=mime_type,
            file_name=normalized.rsplit("/", 1)[-1],
            size_bytes=len(data),
            occurred_at=occurred_at,
            status=INGEST_STATUS_QUEUED,
            stage="Queued",
            progress_pct=0,
        )
        try:
            # A savepoint keeps the request transaction and its RLS context
            # usable when the partial unique index rejects the enqueue.
            async with self.repository.session.begin_nested():
                await self.repository.add(job)
        except IntegrityError as exc:
            await self._discard_storage(storage_key, storage_backend)
            raise IngestJobConflictError(normalized) from exc
        except Exception:
            await self._discard_storage(storage_key, storage_backend)
            raise
        await self._notify(job.id)
        return _to_schema(job)

    async def enqueue_text(
        self,
        *,
        path: str,
        content: str,
        occurred_at: datetime | None,
    ) -> IngestJobSchema:
        """Store the exact text as the original and queue a background ingest."""
        normalized = self.file_service.normalize_path(path)
        encoded = content.encode("utf-8")
        if len(encoded) > self.file_service.max_text_bytes:
            raise FileTooLargeError(len(encoded), self.file_service.max_text_bytes)
        mime_type = mimetypes.guess_type(normalized)[0] or "text/plain"
        storage_key = self.file_service.new_storage_key(
            self.user_id,
            extension(normalized),
        )
        storage_backend = self.file_service.storage_backend
        await self._store_payload(storage_key, encoded, storage_backend)
        job = FileIngestJobModel(
            user_id=self.user_id,
            source_kind=INGEST_SOURCE_TEXT,
            path=normalized,
            storage_key=storage_key,
            storage_backend=storage_backend,
            mime_type=mime_type,
            file_name=normalized.rsplit("/", 1)[-1],
            size_bytes=len(encoded),
            occurred_at=occurred_at,
            status=INGEST_STATUS_QUEUED,
            stage="Queued",
            progress_pct=0,
        )
        try:
            async with self.repository.session.begin_nested():
                await self.repository.add(job)
        except IntegrityError as exc:
            await self._discard_storage(storage_key, storage_backend)
            raise IngestJobConflictError(normalized) from exc
        except Exception:
            await self._discard_storage(storage_key, storage_backend)
            raise
        await self._notify(job.id)
        return _to_schema(job)

    async def get_job(self, job_id: int) -> IngestJobSchema:
        job = await self.repository.get(job_id)
        if job is None:
            raise IngestJobNotFoundError(job_id)
        return _to_schema(job)

    async def enqueue_reingest(
        self,
        file_id: int,
        *,
        expected_version: int,
    ) -> IngestJobSchema:
        """Queue a vision re-extraction that creates a new file version."""
        source = await self.file_service.get_reingest_source(
            file_id,
            expected_version=expected_version,
        )
        mode = vision_mode_for_extension(source.path)
        if mode is None:  # pragma: no cover - get_reingest_source already rejects
            raise UnsupportedFileTypeError(source.extension)
        job = FileIngestJobModel(
            user_id=self.user_id,
            source_kind=INGEST_SOURCE_REINGEST,
            source_file_id=source.file_id,
            path=source.path,
            storage_key=None,
            storage_backend=None,
            mime_type=source.mime_type,
            file_name=source.file_name,
            size_bytes=source.size_bytes,
            occurred_at=source.created_at,
            status=INGEST_STATUS_QUEUED,
            stage=f"Queued {mode} re-ingest",
            progress_pct=0,
        )
        try:
            async with self.repository.session.begin_nested():
                await self.repository.add(job)
        except IntegrityError as exc:
            raise IngestJobConflictError(source.path) from exc
        await self._notify(job.id)
        return _to_schema(job)

    async def list_jobs(self, *, limit: int, offset: int) -> IngestJobListSchema:
        jobs = await self.repository.list_recent(limit=limit, offset=offset)
        total = await self.repository.count()
        return IngestJobListSchema(
            total_results=total,
            jobs=[_to_schema(job) for job in jobs],
        )

    async def retry_job(self, job_id: int) -> IngestJobSchema:
        """Return a failed job to the queue without resetting its attempt count."""
        job = await self.repository.get(job_id)
        if job is None:
            raise IngestJobNotFoundError(job_id)
        if job.status != INGEST_STATUS_FAILED:
            raise IngestJobNotRetryableError(job_id, "the job has not failed")
        if job.attempts >= self.max_attempts:
            raise IngestJobNotRetryableError(job_id, "the attempt limit was reached")
        job.status = INGEST_STATUS_QUEUED
        job.stage = "Retry queued"
        job.progress_pct = 0
        job.stage_done = None
        job.stage_total = None
        job.stage_unit = None
        job.chunks_total = None
        job.chunks_embedded = None
        job.error_code = None
        job.error_detail = None
        job.finished_at = None
        job.started_at = None
        job.updated_at = utcnow()
        try:
            async with self.repository.session.begin_nested():
                await self.repository.session.flush()
        except IntegrityError as exc:
            raise IngestJobConflictError(job.path) from exc
        return _to_schema(job)


class _JobProgress(IngestProgressProtocol):
    """Persist ingestion milestones and report granular parse/chunk progress.

    ``file_created`` runs after the worker's file/node checkpoint, so the
    staged file row is already committed when the job stores its foreign key.

    Every write goes through one per-job lock. The reporter and the pipeline's
    milestone callbacks share it, so a slow report cannot overwrite a later
    milestone with an older status or percentage.
    """

    def __init__(
        self,
        worker: "IngestWorker",
        job_id: int,
        user_id: int,
        tracker: ProgressTracker,
        progress_bus: ProgressBusProtocol | None = None,
    ) -> None:
        self.worker = worker
        self.job_id = job_id
        self.user_id = user_id
        self.tracker = tracker
        self.progress_bus = progress_bus
        self.file_id: int | None = None
        self.embedded_count: int | None = None
        self._last_pct = 0
        self._lock = asyncio.Lock()

    def _raise_high_water(self, value: int) -> int:
        """Record and return the highest percentage this job has published."""
        self._last_pct = max(self._last_pct, value)
        return self._last_pct

    async def chunked(self, total: int) -> None:
        async with self._lock:
            self.tracker.finish()
            await self.worker.update_job(
                self.job_id,
                self.user_id,
                status=INGEST_STATUS_CHUNKING,
                stage="Splitting text into chunks",
                progress_pct=self._raise_high_water(60),
                stage_done=None,
                stage_total=None,
                stage_unit=None,
                chunks_total=total,
            )

    async def file_created(self, file_id: int) -> None:
        self.file_id = file_id
        async with self._lock:
            await self.worker.update_job(self.job_id, self.user_id, file_id=file_id)

    async def embedded(self, done: int, total: int) -> None:
        self.embedded_count = done
        ratio = 0.0 if total <= 0 else done / total
        async with self._lock:
            self.tracker.finish()
            await self.worker.update_job(
                self.job_id,
                self.user_id,
                status=INGEST_STATUS_EMBEDDING,
                stage=f"Embedding chunks {done}/{total}",
                progress_pct=self._raise_high_water(min(92, 60 + int(32 * ratio))),
                stage_done=None,
                stage_total=None,
                stage_unit=None,
                chunks_embedded=done,
            )

    async def announce(self, **fields: Any) -> None:
        """Write a pipeline transition under the same lock as the reporter.

        The reporter can be mid-tick when extraction hands off to chunking or
        publication. Serializing both writers keeps the published status and
        percentage monotonic. A chunking announcement also moves the tracker
        out of parsing with an unknown total, so a reporter tick before the
        chunker starts cannot revert the status or republish parse counts.
        """
        async with self._lock:
            if fields.get("status") == INGEST_STATUS_CHUNKING:
                self.tracker.begin(PHASE_CHUNKING, 0, "chunk")
            if "progress_pct" in fields:
                raw = fields["progress_pct"]
                if isinstance(raw, int):
                    fields["progress_pct"] = self._raise_high_water(raw)
            await self.worker.update_job(self.job_id, self.user_id, **fields)

    async def report(self) -> None:
        """Write one granular snapshot, or just refresh the lease when idle.

        Called once per second by the job's reporter task. An unchanged snapshot
        still writes ``updated_at`` so a long embedding pass keeps the lease
        fresh. Once the tracker is idle the DB keeps the embedding milestone and
        this method only heartbeats.

        Parsing and chunking percentages use a per-job high-water mark. A
        second parsing pass (PDF text, then rendered vision pages, or DOCX text,
        then images) legitimately restarts its unit count, but the overall bar
        must never move backwards.
        """
        async with self._lock:
            snapshot = self.tracker.snapshot()
            fields: dict[str, Any] = {}
            if snapshot.phase == PHASE_PARSING:
                total = snapshot.total or 0
                done = snapshot.done
                progress_pct = 5 + int(40 * done / total) if total > 0 else 5
                fields = {
                    "status": INGEST_STATUS_PARSING,
                    "stage": f"Extracting {done}/{total} {snapshot.unit or 'unit'}",
                    "progress_pct": self._raise_high_water(min(45, progress_pct)),
                    "stage_done": done if total > 0 else None,
                    "stage_total": total if total > 0 else None,
                    "stage_unit": snapshot.unit if total > 0 else None,
                }
            elif snapshot.phase == PHASE_CHUNKING:
                total = snapshot.total or 0
                done = snapshot.done
                progress_pct = 45 + int(15 * done / total) if total > 0 else 45
                fields = {
                    "status": INGEST_STATUS_CHUNKING,
                    "stage": f"Chunking {done}/{total} chunks",
                    "progress_pct": self._raise_high_water(min(60, progress_pct)),
                    "stage_done": done if total > 0 else None,
                    "stage_total": total if total > 0 else None,
                    "stage_unit": snapshot.unit if total > 0 else None,
                }
            await self.worker.update_job(self.job_id, self.user_id, **fields)


class IngestWorker:
    """Bounded polling worker for the durable ingestion queue.

    Queue maintenance (claim, stale listing, requeue) uses
    ``maintenance_session`` because it must see rows across owners. Immediately
    after a claim, all file/chunk work switches to
    ``user_session(job.user_id, "user")``. Parsing and chunking run through one
    bounded ``ThreadPoolExecutor`` shared by the worker's file services; a job
    semaphore caps how many jobs are in flight.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        file_service_factory: FileServiceFactory,
        storage: FileStorageProtocol,
        max_attempts: int,
        runtime_config: IngestRuntimeConfig,
        config_provider: Callable[[], Awaitable[IngestRuntimeConfig]] | None = None,
        provider_refresh: Callable[[], Awaitable[EmbedderProtocol]] | None = None,
        stale_seconds: int = 300,
        extract_pool: ThreadPoolExecutor | None = None,
        extract_semaphore: asyncio.Semaphore | None = None,
        embedding_semaphore: asyncio.Semaphore | None = None,
        progress_bus: ProgressBusProtocol | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.file_service_factory = file_service_factory
        self.storage = storage
        self.max_attempts = max(1, max_attempts)
        self.stale_seconds = max(1, stale_seconds)
        self.extract_pool = extract_pool
        self.config_provider = config_provider
        self.provider_refresh = provider_refresh
        self.progress_bus = progress_bus
        self.runtime_config = runtime_config
        self.poll_seconds = runtime_config.poll_seconds
        self.extract_workers = runtime_config.extract_workers
        self.max_in_flight_jobs = runtime_config.max_inflight_jobs
        self.embedding_concurrency = runtime_config.embedding_concurrency
        self.extract_semaphore = extract_semaphore or asyncio.Semaphore(self.extract_workers)
        self.embedding_semaphore = embedding_semaphore or asyncio.Semaphore(
            self.embedding_concurrency
        )
        self._job_slots = asyncio.Semaphore(self.max_in_flight_jobs)

    def _runtime(self) -> _WorkerRuntime:
        """Capture one immutable runtime bundle for a newly claimed job."""
        return _WorkerRuntime(
            config=self.runtime_config,
            extract_semaphore=self.extract_semaphore,
            embedding_semaphore=self.embedding_semaphore,
            job_slots=self._job_slots,
        )

    async def _refresh_runtime(self) -> None:
        """Pick up database settings without disturbing in-flight jobs."""
        if self.config_provider is None:
            return
        try:
            config = await self.config_provider()
        except Exception:
            logger.exception("Could not refresh ingestion runtime settings")
            return
        previous = self.runtime_config
        if config.extract_workers != previous.extract_workers:
            self.extract_semaphore = asyncio.Semaphore(config.extract_workers)
        if config.embedding_concurrency != previous.embedding_concurrency:
            self.embedding_semaphore = asyncio.Semaphore(config.embedding_concurrency)
        if config.max_inflight_jobs != previous.max_inflight_jobs:
            self._job_slots = asyncio.Semaphore(config.max_inflight_jobs)
        self.runtime_config = config
        self.poll_seconds = config.poll_seconds
        self.extract_workers = config.extract_workers
        self.max_in_flight_jobs = config.max_inflight_jobs
        self.embedding_concurrency = config.embedding_concurrency

    async def _refresh_provider_runtime(self) -> None:
        """Reload provider configuration at a batch boundary.

        Called only when the worker has no claimed job in flight. A job builds
        its file service after the claim and keeps that embedder and text
        generator for its whole pipeline, so a key, model, base URL, or
        dimension change applies to the next batch instead of mutating a
        running job. A failed refresh keeps the previous snapshot usable.
        """
        if self.provider_refresh is None:
            return
        try:
            await self.provider_refresh()
        except Exception:
            logger.exception("Could not refresh the AI provider runtime")

    def close(self) -> None:
        """Release extraction threads without waiting on a stopped event loop."""
        if self.extract_pool is not None:
            self.extract_pool.shutdown(wait=False, cancel_futures=True)

    async def startup(self) -> int:
        """Requeue jobs abandoned by a previous process before polling starts.

        Staged file versions from the interrupted attempt are deleted inside the
        job owner's RLS context first, so a restart cannot leave invisible rows
        behind. Terminal recoveries also remove their stored payloads with the
        backend recorded on the job.
        """
        await self._refresh_runtime()
        runtime = self._runtime()
        stale_before = utcnow() - timedelta(seconds=self.stale_seconds)
        async with maintenance_session(self.session_factory) as session:
            stale_jobs = await IngestJobRepository(session).list_stale(
                stale_before=stale_before
            )
            stale = [(job.id, job.user_id, job.file_id) for job in stale_jobs]
        for job_id, user_id, file_id in stale:
            if file_id is None:
                continue
            # Keep updated_at stale so the requeue query below still sees this
            # row after the staged file is removed.
            await self._discard_staged_file(job_id, user_id, file_id, runtime)

        async with maintenance_session(self.session_factory) as session:
            recovered, terminal_payloads = await IngestJobRepository(session).requeue_stale(
                stale_before=stale_before,
                max_attempts=self.max_attempts,
            )
        for storage_key, storage_backend in terminal_payloads:
            await self._delete_payload(storage_key, storage_backend)
        if recovered:
            logger.warning("Requeued %d interrupted ingestion job(s)", recovered)
        return recovered

    async def _read_payload(self, storage_key: str | None, storage_backend: str | None) -> bytes:
        """Read one job payload with provider-safe error translation."""
        if storage_key is None:
            raise FileNotFoundError("The job payload is missing.")
        try:
            return await self.storage.read(storage_key, backend=storage_backend)
        except StorageObjectMissingError as exc:
            raise FileNotFoundError("The job payload is missing.") from exc
        except (StorageUnavailableError, StorageError, OSError) as exc:
            raise FileStorageUnavailableError() from exc

    async def _delete_payload(
        self,
        storage_key: str | None,
        storage_backend: str | None,
    ) -> None:
        """Remove a temporary or terminal payload without failing the job."""
        if storage_key is None:
            return
        try:
            await self.storage.delete(storage_key, backend=storage_backend)
        except Exception:
            logger.warning("Could not delete ingestion payload %s", storage_key)

    async def _discard_staged_file(
        self,
        job_id: int,
        user_id: int,
        file_id: int,
        runtime: _WorkerRuntime,
    ) -> None:
        """Remove one interrupted attempt's staged file inside the owner's RLS.

        ``clear_file_id`` keeps ``updated_at`` stale so startup recovery and the
        single-job notifier recovery can still see the row afterwards.
        """
        try:
            async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                repository = IngestJobRepository(session, user_id)
                await repository.clear_file_id(job_id)
                file_service = await self.file_service_factory(
                    session,
                    user_id,
                    runtime.config,
                    runtime.extract_semaphore,
                    runtime.embedding_semaphore,
                    None,
                )
                await file_service.discard_pending(file_id)
        except Exception:
            logger.exception(
                "Could not discard staged file %d during recovery",
                file_id,
            )

    async def _discard_requeued_file(
        self,
        user_id: int,
        file_id: int,
        runtime: _WorkerRuntime,
    ) -> None:
        """Delete the staged file detached by an atomic stale-job requeue.

        The row already has ``file_id = NULL`` from the locked requeue, so this
        path must not call ``clear_file_id`` again. Deleting only the captured
        id keeps a concurrent heartbeat or a live worker's staging untouched.
        """
        try:
            async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                file_service = await self.file_service_factory(
                    session,
                    user_id,
                    runtime.config,
                    runtime.extract_semaphore,
                    runtime.embedding_semaphore,
                    None,
                )
                await file_service.discard_pending(file_id)
        except Exception:
            logger.exception(
                "Could not discard staged file %d during recovery",
                file_id,
            )

    async def run_once(self) -> bool:
        """Claim and fully process at most one queued job."""
        await self._refresh_provider_runtime()
        await self._refresh_runtime()
        claimed = await self._claim_next()
        if claimed is None:
            return False
        job_id, user_id = claimed
        await self._process_claimed(job_id, user_id, self._runtime())
        return True

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Poll immediately and keep up to ``max_in_flight_jobs`` jobs running.

        A claimed job is started before the next poll, so a full queue drains
        without extra delay while an empty queue waits ``poll_seconds`` (one
        second by default). Progress updates remain per job because each task
        owns its own sessions.
        """
        tasks: set[asyncio.Task[None]] = set()
        try:
            while stop_event is None or not stop_event.is_set():
                for finished in {task for task in tasks if task.done()}:
                    tasks.discard(finished)
                # Provider changes are visible only between batches. Refreshing
                # while any claimed job is still running would let a routine
                # key/model edit change the clients underneath that job.
                if not tasks:
                    await self._refresh_provider_runtime()
                await self._refresh_runtime()
                runtime = self._runtime()
                while len(tasks) < runtime.config.max_inflight_jobs:
                    try:
                        claimed = await self._claim_next()
                    except Exception:
                        logger.exception("Could not claim an ingestion job")
                        break
                    if claimed is None:
                        break
                    job_id, user_id = claimed
                    tasks.add(
                        asyncio.create_task(
                            self._process_with_slot(job_id, user_id, runtime),
                            name=f"ingest-job-{job_id}",
                        )
                    )
                if tasks:
                    await asyncio.wait(
                        tasks,
                        timeout=self.poll_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue
                if stop_event is not None:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=self.poll_seconds,
                        )
                    except TimeoutError:
                        pass
                else:
                    await asyncio.sleep(self.poll_seconds)
        finally:
            if stop_event is not None and stop_event.is_set() and tasks:
                # A signal asked for a graceful stop: let claimed jobs finish.
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_with_slot(
        self,
        job_id: int,
        user_id: int,
        runtime: _WorkerRuntime,
    ) -> None:
        """Hold one in-flight slot for the whole job pipeline."""
        try:
            async with runtime.job_slots:
                await self._process_claimed(job_id, user_id, runtime)
        except Exception:
            logger.exception("Ingestion job %d crashed", job_id)

    async def process_notified_job(self, job_id: int) -> NotifiedJobOutcome:
        """Process one job named by a broker wake-up message.

        The message is a hint, never a state source. The status is re-read from
        PostgreSQL while holding an in-flight slot, so a duplicate, late, or
        crash-redelivered delivery cannot run a terminal job again. A processing
        row that is still fresh returns ``retry``; an expired lease is recovered
        for exactly this job before it is claimed.
        """
        await self._refresh_runtime()
        runtime = self._runtime()
        stale_before = utcnow() - timedelta(seconds=self.stale_seconds)
        async with runtime.job_slots:
            async with maintenance_session(self.session_factory) as session:
                job = await IngestJobRepository(session).get(job_id)
                if job is None:
                    return "missing"
                status = job.status
                updated_at = job.updated_at
            if status in (INGEST_STATUS_READY, INGEST_STATUS_FAILED):
                return "terminal"
            if status == INGEST_STATUS_QUEUED:
                return await self._claim_notified(job_id, runtime)
            if status not in INGEST_PROCESSING_STATUSES:
                return "terminal"
            if updated_at >= stale_before:
                # Another worker still owns a live lease; let the consumer use
                # the retry queue instead of competing for the row.
                return "retry"
            return await self._recover_notified(job_id, runtime)

    async def _claim_notified(
        self,
        job_id: int,
        runtime: _WorkerRuntime,
    ) -> NotifiedJobOutcome:
        """Claim one specific queued row, or classify why it was not claimable."""
        async with maintenance_session(self.session_factory) as session:
            repository = IngestJobRepository(session)
            job = await repository.claim(job_id)
            if job is None:
                current = await repository.get(job_id)
                if current is None:
                    return "missing"
                if current.status in (INGEST_STATUS_READY, INGEST_STATUS_FAILED):
                    return "terminal"
                return "retry"
            user_id = job.user_id
        await self._process_claimed(job_id, user_id, runtime)
        return "processed"

    async def _recover_notified(
        self,
        job_id: int,
        runtime: _WorkerRuntime,
    ) -> NotifiedJobOutcome:
        """Requeue one expired processing lease without consuming an attempt.

        ``requeue_one`` atomically detaches any staged file while holding the
        row lock, so the returned file id can only belong to the attempt that
        lost its lease. A heartbeat or another worker that won the race returns
        ``None`` and nothing is deleted.
        """
        stale_before = utcnow() - timedelta(seconds=self.stale_seconds)
        async with maintenance_session(self.session_factory) as session:
            requeued = await IngestJobRepository(session).requeue_one(
                job_id,
                stale_before=stale_before,
            )
        if requeued is None:
            # The status changed while this message was in flight; the retry
            # queue re-evaluates it from the database later.
            return "retry"
        if requeued.old_file_id is not None:
            await self._discard_requeued_file(
                requeued.user_id,
                requeued.old_file_id,
                runtime,
            )
        return await self._claim_notified(job_id, runtime)

    async def process_job(self, job_id: int) -> IngestJobSchema | None:
        """Claim and process one specific queued job (tests and ``--once``)."""
        await self._refresh_provider_runtime()
        await self._refresh_runtime()
        async with maintenance_session(self.session_factory) as session:
            job = await IngestJobRepository(session).claim(job_id)
            if job is None:
                return None
            user_id = job.user_id
        await self._process_claimed(job_id, user_id, self._runtime())
        return await self.get_job(job_id, user_id)

    async def get_job(self, job_id: int, user_id: int) -> IngestJobSchema | None:
        async with user_session(self.session_factory, user_id, ROLE_USER) as session:
            job = await IngestJobRepository(session, user_id).get(job_id)
            return None if job is None else _to_schema(job)

    async def update_job(
        self,
        job_id: int,
        user_id: int,
        **fields: Any,
    ) -> IngestJobSchema | None:
        """Apply one progress update in the job owner's scoped transaction.

        The compact event is published only after the scoped session commits.
        The returned schema lets callers that need the committed row reuse it;
        existing callers may ignore the value.
        """
        updated: FileIngestJobModel | None = None
        async with user_session(self.session_factory, user_id, ROLE_USER) as session:
            job = await IngestJobRepository(session, user_id).get(job_id)
            if job is None:
                return None
            for name, value in fields.items():
                setattr(job, name, value)
            job.updated_at = utcnow()
            await session.flush()
            updated = job
        if updated is None:  # pragma: no cover - the branch above already returned
            return None
        schema = _to_schema(updated)
        await self._publish_progress(schema)
        return schema

    async def _publish_progress(self, schema: IngestJobSchema) -> None:
        """Publish one compact event; a broker failure never fails the job."""
        if self.progress_bus is None:
            return
        try:
            await asyncio.wait_for(
                self.progress_bus.publish(
                    IngestProgressEventSchema.model_validate(schema)
                ),
                timeout=PROGRESS_PUBLISH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Could not publish progress for ingestion job %d (%s)",
                schema.id,
                type(exc).__name__,
            )

    async def _claim_next(self) -> ClaimedJob | None:
        async with maintenance_session(self.session_factory) as session:
            job = await IngestJobRepository(session).claim_next()
            if job is None:
                return None
            return job.id, job.user_id

    async def _process_claimed(
        self,
        job_id: int,
        user_id: int,
        runtime: _WorkerRuntime,
    ) -> None:
        job = await self._load_job(job_id, user_id)
        if job is None:
            return
        tracker = ProgressTracker()
        progress = _JobProgress(
            self,
            job_id,
            user_id,
            tracker,
            self.progress_bus,
        )
        staged_file_id: int | None = None
        source: ReingestSource | None = None
        storage_key: str | None = None
        storage_backend: str | None = None
        occurred_at: datetime | None = None
        reporter = asyncio.create_task(
            self._report_progress_forever(progress),
            name=f"ingest-progress-{job_id}",
        )
        try:
            if job.source_kind == INGEST_SOURCE_REINGEST:
                if job.source_file_id is None:
                    raise IngestSourceStaleError(job.id)
                async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                    source_service = await self.file_service_factory(
                        session,
                        user_id,
                        runtime.config,
                        runtime.extract_semaphore,
                        runtime.embedding_semaphore,
                        tracker,
                    )
                    source = await source_service.get_reingest_source_by_file_id(
                        job.source_file_id,
                        expected_path=job.path,
                    )
                # The source original is shared with the current file version;
                # read it after the locking transaction closes.
                data = await source_service.read_reingest_bytes(source)
                storage_key = source.storage_key
                storage_backend = source.storage_backend
                occurred_at = source.created_at
                force_vision = True
            else:
                data = await self._read_payload(job.storage_key, job.storage_backend)
                storage_key = job.storage_key
                storage_backend = job.storage_backend
                occurred_at = job.occurred_at
                force_vision = False

            async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                file_service = await self.file_service_factory(
                    session,
                    user_id,
                    runtime.config,
                    runtime.extract_semaphore,
                    runtime.embedding_semaphore,
                    tracker,
                )
                extracted = await file_service.prepare_job_document(
                    source_kind=job.source_kind,
                    path=job.path,
                    data=data,
                    force_vision=force_vision,
                )
                # Announce chunking before chunk_text starts. announce() moves
                # the tracker out of parsing and clears the stale parse counts,
                # so a reporter tick cannot show "Chunking · 10/10 pages".
                await progress.announce(
                    status=INGEST_STATUS_CHUNKING,
                    stage="Splitting text into chunks",
                    progress_pct=45,
                    stage_done=None,
                    stage_total=None,
                    stage_unit=None,
                )

                async def checkpoint() -> None:
                    """Commit staged rows and immediately restore the owner context."""
                    await commit_and_reapply(session, user_id, ROLE_USER)

                file_schema = await file_service.ingest_extracted(
                    path=job.path,
                    data=data,
                    extracted=extracted,
                    mime_type=job.mime_type,
                    storage_key=storage_key,
                    storage_backend=storage_backend,
                    occurred_at=occurred_at,
                    publish=False,
                    progress=progress,
                    checkpoint=checkpoint,
                )
            staged_file_id = file_schema.id

            await progress.announce(
                file_id=file_schema.id,
                status=INGEST_STATUS_SUMMARIZING,
                stage="Publishing file",
                progress_pct=95,
                stage_done=None,
                stage_total=None,
                stage_unit=None,
            )
            expected_current_file_id = source.file_id if source is not None else None
            ready_schema: IngestJobSchema | None = None
            async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                file_service = await self.file_service_factory(
                    session,
                    user_id,
                    runtime.config,
                    runtime.extract_semaphore,
                    runtime.embedding_semaphore,
                    tracker,
                )
                await file_service.publish_pending(
                    file_schema.id,
                    expected_current_file_id=expected_current_file_id,
                )
                ready_job = await IngestJobRepository(session, user_id).get(job_id)
                if ready_job is not None:
                    ready_job.status = INGEST_STATUS_READY
                    ready_job.stage = "Ready"
                    ready_job.progress_pct = 100
                    ready_job.stage_done = None
                    ready_job.stage_total = None
                    ready_job.stage_unit = None
                    ready_job.chunks_embedded = progress.embedded_count
                    ready_job.file_id = file_schema.id
                    ready_job.finished_at = utcnow()
                    ready_job.updated_at = utcnow()
                    ready_schema = _to_schema(ready_job)
            if ready_schema is not None:
                await self._publish_progress(ready_schema)
        except Exception as exc:
            # Stop granular writes before the terminal failure so a reporter
            # tick cannot publish parsing/chunking after the job has failed.
            tracker.finish()
            reporter.cancel()
            with suppress(asyncio.CancelledError):
                await reporter
            logger.exception("Ingestion job %d failed", job_id)
            await self._fail(
                job_id,
                user_id,
                exc,
                runtime,
                progress.file_id or staged_file_id,
            )
        finally:
            reporter.cancel()
            with suppress(asyncio.CancelledError):
                await reporter

    def _report_interval(self) -> float:
        """Report granular progress once per second and keep the lease fresh."""
        return 1.0

    async def _report_progress_forever(self, progress: _JobProgress) -> None:
        """Write tracker snapshots until the job's reporter is cancelled.

        The same loop is the lease heartbeat: an unchanged snapshot still
        touches ``updated_at``. Long extractions therefore never look like an
        abandoned lease to another worker, and the job row stays the single
        heartbeat source.
        """
        while True:
            await asyncio.sleep(self._report_interval())
            try:
                await progress.report()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Could not refresh progress for ingestion job %d",
                    progress.job_id,
                )

    async def _load_job(self, job_id: int, user_id: int) -> FileIngestJobModel | None:
        async with user_session(self.session_factory, user_id, ROLE_USER) as session:
            return await IngestJobRepository(session, user_id).get(job_id)

    async def _fail(
        self,
        job_id: int,
        user_id: int,
        exc: BaseException,
        runtime: _WorkerRuntime,
        staged_file_id: int | None = None,
    ) -> None:
        job = await self._load_job(job_id, user_id)
        if job is None:
            return
        file_id = job.file_id if job.file_id is not None else staged_file_id
        discarded = False
        if file_id is not None:
            # Clear the foreign key first: the file row uses ON DELETE CASCADE,
            # so deleting the staged file would otherwise delete the job too.
            await self.update_job(job_id, user_id, file_id=None)
            async with user_session(self.session_factory, user_id, ROLE_USER) as session:
                file_service = await self.file_service_factory(
                    session,
                    user_id,
                    runtime.config,
                    runtime.extract_semaphore,
                    runtime.embedding_semaphore,
                    None,
                )
                discarded = await file_service.discard_pending(file_id)
        can_delete_payload = (file_id is None or discarded) and (
            job.source_kind != INGEST_SOURCE_REINGEST
        )
        if job.attempts >= self.max_attempts and can_delete_payload:
            await self._delete_payload(job.storage_key, job.storage_backend)
        detail = str(exc) or exc.__class__.__name__
        await self.update_job(
            job_id,
            user_id,
            status=INGEST_STATUS_FAILED,
            stage="Failed",
            error_code=ingest_error_code(exc),
            error_detail=detail[:2000],
            file_id=None,
            stage_done=None,
            stage_total=None,
            stage_unit=None,
            finished_at=utcnow(),
        )


__all__ = [
    "IngestJobService",
    "IngestWorker",
    "ingest_error_code",
]
