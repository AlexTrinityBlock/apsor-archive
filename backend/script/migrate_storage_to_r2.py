"""Migrate original bytes from local storage to Cloudflare R2.

Run from the backend directory:

    uv run python -m script.migrate_storage_to_r2 --dry-run
    uv run python -m script.migrate_storage_to_r2 --copy
    uv run python -m script.migrate_storage_to_r2 --verify
    uv run python -m script.migrate_storage_to_r2 --delete-local

Stop the API and the ingestion worker first. The script is intentionally
separate from normal request handling and is safe to re-run: existing R2
objects are verified and skipped, and database rows are updated only after the
remote bytes match the local content hash.

``--delete-local`` is never implied. It verifies the remote object and every
mapped database row before unlinking one local key, and it never touches
``data/.secret_key`` or any file that is not referenced by a storage row.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.files.r2_storage import R2FileStorage
from app.infrastructure.files.storage_errors import StorageError
from app.infrastructure.logger.logging import configure_logging

logger = logging.getLogger("apsor.storage_migration")

_FILE_ROWS_SQL = text(
    """
    SELECT id, storage_key, size_bytes, content_hash, storage_backend
    FROM file
    WHERE storage_key IS NOT NULL AND storage_key <> ''
    ORDER BY id
    """
)

_JOB_ROWS_SQL = text(
    """
    SELECT id, storage_key, size_bytes, storage_backend
    FROM file_ingest_job
    WHERE storage_key IS NOT NULL AND storage_key <> ''
      AND (
          status IN ('queued', 'parsing', 'chunking', 'embedding', 'summarizing')
          OR (status = 'failed' AND attempts < :max_attempts)
      )
    ORDER BY id
    """
)

_MARK_FILE_R2_SQL = text("UPDATE file SET storage_backend = 'r2' WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)

_MARK_JOB_R2_SQL = text(
    "UPDATE file_ingest_job SET storage_backend = 'r2' WHERE id IN :ids"
).bindparams(bindparam("ids", expanding=True))


class MigrationFailure(RuntimeError):
    """One object failed verification or cannot be migrated safely."""


@dataclass(frozen=True, slots=True)
class FileRow:
    id: int
    size_bytes: int
    content_hash: str
    storage_backend: str | None


@dataclass(frozen=True, slots=True)
class JobRow:
    id: int
    size_bytes: int
    storage_backend: str | None


@dataclass(slots=True)
class MigrationObject:
    key: str
    files: list[FileRow] = field(default_factory=list)
    jobs: list[JobRow] = field(default_factory=list)

    @property
    def expected_size(self) -> int:
        sizes = {row.size_bytes for row in self.files} | {row.size_bytes for row in self.jobs}
        if not sizes:
            raise MigrationFailure("No database row owns this storage key.")
        if len(sizes) != 1:
            raise MigrationFailure("Database rows disagree about the object size.")
        return sizes.pop()

    @property
    def expected_hash(self) -> str | None:
        hashes = {row.content_hash for row in self.files}
        if len(hashes) > 1:
            raise MigrationFailure("Database rows disagree about the content hash.")
        return next(iter(hashes), None)

    @property
    def rows_are_r2(self) -> bool:
        rows = [row.storage_backend for row in self.files]
        rows.extend(row.storage_backend for row in self.jobs)
        return bool(rows) and all(backend == "r2" for backend in rows)


@dataclass(frozen=True, slots=True)
class Mode:
    dry_run: bool
    copy: bool
    verify: bool
    delete_local: bool


def _parse_args(argv: Sequence[str] | None) -> Mode:
    parser = argparse.ArgumentParser(
        description="Migrate Apsor Archive original bytes from local storage to R2.",
        epilog=("Run from backend/: uv run python -m script.migrate_storage_to_r2 --dry-run"),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned work and local integrity problems without remote or DB writes.",
    )
    group.add_argument(
        "--copy",
        action="store_true",
        help="Upload missing objects, verify them, then mark rows storage_backend='r2'.",
    )
    group.add_argument(
        "--verify",
        action="store_true",
        help="Verify R2 bytes and that every row is marked storage_backend='r2'.",
    )
    group.add_argument(
        "--delete-local",
        action="store_true",
        help="After re-verifying R2, delete one referenced local object at a time.",
    )
    arguments = parser.parse_args(argv)
    return Mode(
        dry_run=arguments.dry_run,
        copy=arguments.copy,
        verify=arguments.verify,
        delete_local=arguments.delete_local,
    )


def _local_path(data_dir: Path, key: str) -> Path:
    root = data_dir.resolve()
    candidate = (root / key).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise MigrationFailure(f"Storage key escapes the data directory: {key}")
    if candidate == (root / ".secret_key").resolve():
        raise MigrationFailure("Refusing to operate on the archive master key.")
    return candidate


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _bypass_rls_or_fail(session: AsyncSession) -> None:
    """Run maintenance reads/writes as a superuser or fail loudly.

    The schema uses FORCE ROW LEVEL SECURITY. A non-superuser owner that does
    not bypass RLS would otherwise see zero rows and silently migrate nothing.
    ``row_security=off`` either bypasses RLS or raises when policies would apply.
    """
    await session.execute(text("SET LOCAL row_security = off"))


def _verify_local_bytes(
    obj: MigrationObject,
    data: bytes,
    *,
    expected_size: int,
    expected_hash: str | None,
) -> str:
    if len(data) != expected_size:
        raise MigrationFailure(
            f"Local size mismatch: found {len(data)} bytes, expected {expected_size}."
        )
    actual_hash = _sha256(data)
    if expected_hash is not None and actual_hash != expected_hash:
        raise MigrationFailure("Local bytes do not match the database content hash.")
    return actual_hash


async def _load_objects(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    max_attempts: int,
) -> dict[str, MigrationObject]:
    async with session_factory() as session:
        await _bypass_rls_or_fail(session)
        file_rows = (await session.execute(_FILE_ROWS_SQL)).mappings().all()
        job_rows = (
            (await session.execute(_JOB_ROWS_SQL, {"max_attempts": max_attempts})).mappings().all()
        )

    objects: dict[str, MigrationObject] = {}
    for row in file_rows:
        key = str(row["storage_key"])
        objects.setdefault(key, MigrationObject(key=key)).files.append(
            FileRow(
                id=int(row["id"]),
                size_bytes=int(row["size_bytes"]),
                content_hash=str(row["content_hash"]),
                storage_backend=row["storage_backend"],
            )
        )
    for row in job_rows:
        key = str(row["storage_key"])
        objects.setdefault(key, MigrationObject(key=key)).jobs.append(
            JobRow(
                id=int(row["id"]),
                size_bytes=int(row["size_bytes"]),
                storage_backend=row["storage_backend"],
            )
        )
    return objects


def _build_r2(settings: Settings) -> R2FileStorage:
    if not settings.r2_configured:
        missing = ", ".join(settings.r2_missing_settings)
        raise MigrationFailure(f"R2 is not configured; missing: {missing}.")
    endpoint_url = settings.r2_endpoint_url
    bucket = settings.r2_bucket
    access_key_id = settings.r2_access_key_id
    secret_access_key = settings.r2_secret_access_key
    if endpoint_url is None or bucket is None or access_key_id is None or secret_access_key is None:
        raise MigrationFailure("R2 configuration is incomplete.")
    return R2FileStorage(
        endpoint_url=endpoint_url,
        bucket=bucket,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=settings.r2_region,
        prefix=settings.r2_prefix,
    )


async def _remote_matches(
    r2: R2FileStorage,
    *,
    key: str,
    expected_size: int,
    expected_hash: str | None,
    local_hash: str | None,
) -> bool:
    """Return True only when the remote bytes are readable and match."""
    remote_size = await r2.head_size(key)
    if remote_size is None or remote_size != expected_size:
        return False
    data = await r2.read(key)
    if len(data) != expected_size:
        return False
    remote_hash = _sha256(data)
    if expected_hash is not None:
        return remote_hash == expected_hash
    if local_hash is not None:
        return remote_hash == local_hash
    # A retryable job payload has no database hash. Size plus a successful
    # GetObject is the strongest check available after local bytes were removed.
    return True


async def _require_remote_match(
    r2: R2FileStorage,
    *,
    key: str,
    expected_size: int,
    expected_hash: str | None,
    local_hash: str | None,
) -> None:
    if not await _remote_matches(
        r2,
        key=key,
        expected_size=expected_size,
        expected_hash=expected_hash,
        local_hash=local_hash,
    ):
        raise MigrationFailure("R2 verification failed: size or SHA-256 did not match.")


async def _mark_rows_r2(
    session_factory: async_sessionmaker[AsyncSession],
    obj: MigrationObject,
) -> None:
    file_ids = [row.id for row in obj.files if row.storage_backend != "r2"]
    job_ids = [row.id for row in obj.jobs if row.storage_backend != "r2"]
    if not file_ids and not job_ids:
        return
    async with session_factory() as session:
        async with session.begin():
            await _bypass_rls_or_fail(session)
            if file_ids:
                await session.execute(_MARK_FILE_R2_SQL, {"ids": file_ids})
            if job_ids:
                await session.execute(_MARK_JOB_R2_SQL, {"ids": job_ids})
    logger.info(
        "  marked %d file row(s) and %d job row(s) as r2",
        len(file_ids),
        len(job_ids),
    )


def _prune_empty_parents(path: Path, *, root: Path) -> None:
    current = path
    while current != root and current.is_relative_to(root):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


async def _copy_object(
    obj: MigrationObject,
    *,
    settings: Settings,
    r2: R2FileStorage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    expected_size = obj.expected_size
    expected_hash = obj.expected_hash
    local_path = _local_path(settings.data_dir, obj.key)
    local_data: bytes | None = None
    local_hash: str | None = None
    if local_path.is_file():
        local_data = await asyncio.to_thread(local_path.read_bytes)
        local_hash = _verify_local_bytes(
            obj,
            local_data,
            expected_size=expected_size,
            expected_hash=expected_hash,
        )
    elif obj.rows_are_r2:
        logger.info("  local object already absent; verifying the R2 copy")
    else:
        raise MigrationFailure("Local object is missing and the rows still point at local.")

    if await _remote_matches(
        r2,
        key=obj.key,
        expected_size=expected_size,
        expected_hash=expected_hash,
        local_hash=local_hash,
    ):
        logger.info("  R2 object already present and verified; skipping upload")
    else:
        if local_data is None:
            raise MigrationFailure("Local object is missing and the R2 copy is not valid.")
        logger.info("  uploading %d byte(s)", len(local_data))
        await r2.save(obj.key, local_data)
        await _require_remote_match(
            r2,
            key=obj.key,
            expected_size=expected_size,
            expected_hash=expected_hash,
            local_hash=local_hash,
        )

    await _mark_rows_r2(session_factory, obj)
    logger.info("  verified and ready on R2")


async def _verify_object(
    obj: MigrationObject,
    *,
    settings: Settings,
    r2: R2FileStorage,
) -> None:
    if not obj.rows_are_r2:
        raise MigrationFailure("One or more database rows are not marked storage_backend='r2'.")
    expected_size = obj.expected_size
    expected_hash = obj.expected_hash
    local_path = _local_path(settings.data_dir, obj.key)
    local_hash: str | None = None
    if local_path.is_file():
        local_data = await asyncio.to_thread(local_path.read_bytes)
        local_hash = _verify_local_bytes(
            obj,
            local_data,
            expected_size=expected_size,
            expected_hash=expected_hash,
        )
    await _require_remote_match(
        r2,
        key=obj.key,
        expected_size=expected_size,
        expected_hash=expected_hash,
        local_hash=local_hash,
    )


async def _run_dry_run(
    objects: dict[str, MigrationObject],
    *,
    settings: Settings,
) -> int:
    failures = 0
    total_bytes = 0
    for index, obj in enumerate(objects.values(), 1):
        try:
            expected_size = obj.expected_size
            expected_hash = obj.expected_hash
            local_path = _local_path(settings.data_dir, obj.key)
            if local_path.is_file():
                data = await asyncio.to_thread(local_path.read_bytes)
                _verify_local_bytes(
                    obj,
                    data,
                    expected_size=expected_size,
                    expected_hash=expected_hash,
                )
                total_bytes += len(data)
                state = "already r2" if obj.rows_are_r2 else "ready to copy"
            elif obj.rows_are_r2:
                state = "local already absent; r2 rows only"
            else:
                raise MigrationFailure("Local object is missing while rows still point at local.")
            logger.info(
                "[%d/%d] %s: %s (%d file row(s), %d job row(s), %d byte(s))",
                index,
                len(objects),
                obj.key,
                state,
                len(obj.files),
                len(obj.jobs),
                expected_size,
            )
        except (MigrationFailure, StorageError, OSError) as exc:
            failures += 1
            logger.error("[%d/%d] %s: FAILED: %s", index, len(objects), obj.key, exc)
    logger.info(
        "Dry run complete: %d unique key(s), %d local byte(s), %d problem(s). "
        "No remote or database writes were performed.",
        len(objects),
        total_bytes,
        failures,
    )
    return 1 if failures else 0


async def _run_copy(
    objects: dict[str, MigrationObject],
    *,
    settings: Settings,
    r2: R2FileStorage,
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    failures = 0
    for index, obj in enumerate(objects.values(), 1):
        logger.info(
            "[%d/%d] copy %s (%d file row(s), %d job row(s))",
            index,
            len(objects),
            obj.key,
            len(obj.files),
            len(obj.jobs),
        )
        try:
            await _copy_object(
                obj,
                settings=settings,
                r2=r2,
                session_factory=session_factory,
            )
        except (MigrationFailure, StorageError, OSError) as exc:
            failures += 1
            logger.error("[%d/%d] %s: FAILED: %s", index, len(objects), obj.key, exc)
        except Exception:
            failures += 1
            logger.exception("[%d/%d] %s: FAILED unexpectedly", index, len(objects), obj.key)
    logger.info("Copy complete: %d key(s), %d failure(s).", len(objects), failures)
    return 1 if failures else 0


async def _run_verify(
    objects: dict[str, MigrationObject],
    *,
    settings: Settings,
    r2: R2FileStorage,
) -> int:
    failures = 0
    for index, obj in enumerate(objects.values(), 1):
        try:
            await _verify_object(obj, settings=settings, r2=r2)
            logger.info(
                "[%d/%d] verified %s (%d file row(s), %d job row(s))",
                index,
                len(objects),
                obj.key,
                len(obj.files),
                len(obj.jobs),
            )
        except (MigrationFailure, StorageError, OSError) as exc:
            failures += 1
            logger.error("[%d/%d] %s: FAILED: %s", index, len(objects), obj.key, exc)
    logger.info("Verify complete: %d key(s), %d failure(s).", len(objects), failures)
    return 1 if failures else 0


async def _run_delete_local(
    objects: dict[str, MigrationObject],
    *,
    settings: Settings,
    r2: R2FileStorage,
) -> int:
    failures = 0
    root = settings.data_dir.resolve()
    for index, obj in enumerate(objects.values(), 1):
        try:
            await _verify_object(obj, settings=settings, r2=r2)
            local_path = _local_path(settings.data_dir, obj.key)
            if not local_path.exists():
                logger.info("[%d/%d] %s: local object already absent", index, len(objects), obj.key)
                continue
            if not local_path.is_file():
                raise MigrationFailure("Local storage key is not a regular file.")
            await asyncio.to_thread(local_path.unlink)
            _prune_empty_parents(local_path.parent, root=root)
            logger.info("[%d/%d] deleted local %s", index, len(objects), obj.key)
        except (MigrationFailure, StorageError, OSError) as exc:
            failures += 1
            logger.error("[%d/%d] %s: FAILED: %s", index, len(objects), obj.key, exc)
    logger.info("Delete-local complete: %d key(s), %d failure(s).", len(objects), failures)
    return 1 if failures else 0


async def _run(settings: Settings, mode: Mode) -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        objects = await _load_objects(
            session_factory,
            max_attempts=max(1, settings.ingest_job_max_attempts),
        )
        if not objects:
            logger.info("No stored objects reference local or R2 bytes; nothing to do.")
            return 0
        logger.info(
            "Found %d unique storage key(s): %d file row(s), %d retryable job row(s).",
            len(objects),
            sum(len(obj.files) for obj in objects.values()),
            sum(len(obj.jobs) for obj in objects.values()),
        )

        if mode.dry_run:
            return await _run_dry_run(objects, settings=settings)

        logger.warning("Confirm the API and ingestion worker are stopped before continuing.")
        if not settings.r2_configured:
            logger.error(
                "R2 is not configured; missing: %s",
                ", ".join(settings.r2_missing_settings),
            )
            return 2
        r2 = _build_r2(settings)

        if mode.copy:
            return await _run_copy(
                objects,
                settings=settings,
                r2=r2,
                session_factory=session_factory,
            )
        if mode.verify:
            return await _run_verify(objects, settings=settings, r2=r2)
        if mode.delete_local:
            return await _run_delete_local(objects, settings=settings, r2=r2)
        raise MigrationFailure("No migration mode was selected.")
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    mode = _parse_args(argv)
    settings = get_settings()
    configure_logging(debug=settings.debug)
    try:
        return asyncio.run(_run(settings, mode))
    except KeyboardInterrupt:
        logger.warning("Storage migration interrupted.")
        return 130
    except MigrationFailure as exc:
        logger.error("Storage migration could not start: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
