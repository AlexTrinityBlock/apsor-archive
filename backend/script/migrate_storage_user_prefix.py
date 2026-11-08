"""Move legacy storage objects under each owner's top-level directory.

Run from the backend directory after stopping the API and ingestion worker:

    uv run python -m script.migrate_storage_user_prefix --dry-run
    uv run python -m script.migrate_storage_user_prefix --apply

The script is deliberately separate from request handling and safe to re-run.
It only considers keys that do not already start with ``users/``; for each
legacy key it reads the bytes, writes ``users/{user_id}/{old_key}``, verifies
the copy, updates every ``file`` and ``file_ingest_job`` row that shares the
key, and then deletes the old object. A failed verification or inconsistent
owner aborts before any database update.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config.settings import get_settings
from app.infrastructure.files.storage_errors import StorageObjectMissingError
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.files.storage_router import StorageRouter
from app.infrastructure.logger.logging import configure_logging

logger = logging.getLogger("apsor.storage_user_prefix")

_FILE_ROWS_SQL = text(
    """
    SELECT storage_key, user_id, storage_backend, content_hash, size_bytes
    FROM file
    WHERE storage_key IS NOT NULL AND storage_key <> ''
    ORDER BY id
    """
)

_JOB_ROWS_SQL = text(
    """
    SELECT storage_key, user_id, storage_backend, size_bytes
    FROM file_ingest_job
    WHERE storage_key IS NOT NULL AND storage_key <> ''
    ORDER BY id
    """
)


class MigrationFailure(RuntimeError):
    """The migration cannot continue without risking a mismatched object."""


@dataclass(slots=True)
class ObjectGroup:
    old_key: str
    user_id: int
    backend: str
    size_bytes: int
    content_hash: str | None
    file_rows: int = 0
    job_rows: int = 0

    @property
    def new_key(self) -> str:
        return f"users/{self.user_id}/{self.old_key}"


def _parse_args(argv: Sequence[str] | None) -> bool:
    parser = argparse.ArgumentParser(
        description="Move legacy file objects under users/{user_id}/...",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="List the planned moves only.")
    mode.add_argument("--apply", action="store_true", help="Copy, verify, update DB, delete old.")
    arguments = parser.parse_args(argv)
    return bool(arguments.apply)


async def _bypass_rls(session: AsyncSession) -> None:
    """The migration reads/writes every owner's rows; require a privileged login."""
    try:
        await session.execute(text("SET LOCAL row_security = off"))
    except Exception as exc:  # pragma: no cover - depends on deployment privileges
        raise MigrationFailure(
            "This migration requires a PostgreSQL role that can bypass row-level security."
        ) from exc


def _add_group(
    groups: dict[str, ObjectGroup],
    *,
    storage_key: str,
    user_id: int,
    storage_backend: str | None,
    default_backend: str,
    size_bytes: int,
    content_hash: str | None,
    is_file: bool,
) -> None:
    if storage_key.startswith("users/"):
        return
    if ".." in storage_key.split("/"):
        raise MigrationFailure(f"Storage key contains a relative segment: {storage_key}")
    backend = storage_backend or default_backend
    existing = groups.get(storage_key)
    if existing is None:
        groups[storage_key] = ObjectGroup(
            old_key=storage_key,
            user_id=user_id,
            backend=backend,
            size_bytes=size_bytes,
            content_hash=content_hash,
            file_rows=1 if is_file else 0,
            job_rows=0 if is_file else 1,
        )
        return
    if existing.user_id != user_id:
        raise MigrationFailure(
            f"Storage key {storage_key} is referenced by more than one user."
        )
    if existing.backend != backend:
        raise MigrationFailure(
            f"Storage key {storage_key} is stored on more than one backend."
        )
    if existing.size_bytes != size_bytes:
        raise MigrationFailure(
            f"Storage key {storage_key} has inconsistent size metadata."
        )
    if content_hash is not None:
        if existing.content_hash is not None and existing.content_hash != content_hash:
            raise MigrationFailure(
                f"Storage key {storage_key} has inconsistent content hashes."
            )
        existing.content_hash = content_hash
    if is_file:
        existing.file_rows += 1
    else:
        existing.job_rows += 1


async def _load_groups(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    default_backend: str,
) -> dict[str, ObjectGroup]:
    async with session_factory() as session:
        await _bypass_rls(session)
        file_rows = (await session.execute(_FILE_ROWS_SQL)).mappings().all()
        job_rows = (await session.execute(_JOB_ROWS_SQL)).mappings().all()

    groups: dict[str, ObjectGroup] = {}
    for row in file_rows:
        _add_group(
            groups,
            storage_key=str(row["storage_key"]),
            user_id=int(row["user_id"]),
            storage_backend=row["storage_backend"],
            default_backend=default_backend,
            size_bytes=int(row["size_bytes"]),
            content_hash=row["content_hash"],
            is_file=True,
        )
    for row in job_rows:
        _add_group(
            groups,
            storage_key=str(row["storage_key"]),
            user_id=int(row["user_id"]),
            storage_backend=row["storage_backend"],
            default_backend=default_backend,
            size_bytes=int(row["size_bytes"]),
            content_hash=None,
            is_file=False,
        )
    return groups


def _verify(label: str, data: bytes, group: ObjectGroup) -> None:
    if len(data) != group.size_bytes:
        raise MigrationFailure(
            f"{label} size mismatch for {group.old_key}: {len(data)} != {group.size_bytes}."
        )
    if group.content_hash is not None:
        digest = hashlib.sha256(data).hexdigest()
        if digest != group.content_hash:
            raise MigrationFailure(f"{label} content hash mismatch for {group.old_key}.")


async def _copy_and_update(
    session_factory: async_sessionmaker[AsyncSession],
    storage: StorageRouter,
    group: ObjectGroup,
) -> None:
    try:
        old_data = await storage.read(group.old_key, backend=group.backend)
    except (StorageObjectMissingError, FileNotFoundError) as exc:
        raise MigrationFailure(f"Missing legacy object: {group.old_key}") from exc
    _verify("Old", old_data, group)

    try:
        new_data = await storage.read(group.new_key, backend=group.backend)
    except (StorageObjectMissingError, FileNotFoundError):
        new_data = None
    if new_data is not None:
        _verify("Existing new", new_data, group)
    else:
        await storage.save(group.new_key, old_data, backend=group.backend)
        copied = await storage.read(group.new_key, backend=group.backend)
        _verify("Copied", copied, group)

    try:
        async with session_factory() as session:
            async with session.begin():
                await _bypass_rls(session)
                file_result = await session.execute(
                    text("UPDATE file SET storage_key = :new WHERE storage_key = :old"),
                    {"new": group.new_key, "old": group.old_key},
                )
                job_result = await session.execute(
                    text(
                        "UPDATE file_ingest_job SET storage_key = :new "
                        "WHERE storage_key = :old"
                    ),
                    {"new": group.new_key, "old": group.old_key},
                )
                file_count = int(getattr(file_result, "rowcount", 0) or 0)
                job_count = int(getattr(job_result, "rowcount", 0) or 0)
                if file_count + job_count == 0:
                    raise MigrationFailure(
                        f"No database row owns storage key {group.old_key}."
                    )
    except Exception:
        # The new object is harmless if the database update failed; leave it for
        # a re-run to verify instead of deleting bytes that may now be referenced.
        raise

    try:
        await storage.delete(group.old_key, backend=group.backend)
    except Exception as exc:  # pragma: no cover - cleanup failure is non-fatal
        logger.warning(
            "Old object could not be deleted; new key is authoritative: %s (%s)",
            group.old_key,
            type(exc).__name__,
        )


async def _run(apply: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = build_file_storage(settings)
    try:
        groups = await _load_groups(
            session_factory,
            default_backend=settings.storage_backend,
        )
        users = sorted({group.user_id for group in groups.values()})
        print(f"legacy_objects={len(groups)} users={users}")
        for group in list(groups.values())[:10]:
            print(f"  {group.old_key} -> {group.new_key}")
        if len(groups) > 10:
            print(f"  ... {len(groups) - 10} more")
        if not apply or not groups:
            return
        for group in groups.values():
            await _copy_and_update(session_factory, storage, group)
            print(f"moved {group.old_key} -> {group.new_key}")
        print(f"migration complete: moved={len(groups)}")
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging(debug=False)
    apply = _parse_args(argv)
    asyncio.run(_run(apply))


if __name__ == "__main__":
    main()
