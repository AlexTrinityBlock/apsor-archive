"""Move already-sent chat images from chat-temp to the durable prefix.

Run from the backend directory after stopping the API and worker:

    uv run python -m script.migrate_chat_attachments_durable --dry-run
    uv run python -m script.migrate_chat_attachments_durable --apply

New messages promote their images before the message claim. This script only
backfills rows that were sent before the durable promotion existed. It is safe
to re-run: rows already under users/{user_id}/chat-images/ are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import text

from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.session import Database
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.logger.logging import configure_logging
from app.module.agent.repository.chat_attachment_repository import (
    ChatAttachmentRepository,
)
from app.module.agent.service.chat_attachment_service import ChatAttachmentService

logger = logging.getLogger("apsor.chat_attachment_durable_migration")

_ATTACHED_TEMP_ROWS_SQL = text(
    """
    SELECT id, user_id
    FROM agent_chat_attachment
    WHERE entry_id IS NOT NULL
      AND deleted_at IS NULL
      AND storage_key LIKE 'users/%/chat-temp/%'
    ORDER BY id
    """
)


def _parse_args(argv: Sequence[str] | None) -> bool:
    parser = argparse.ArgumentParser(
        description="Move sent chat images to users/{user_id}/chat-images/.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="List the planned moves only.")
    mode.add_argument("--apply", action="store_true", help="Copy, verify, update, delete old.")
    arguments = parser.parse_args(argv)
    return bool(arguments.apply)


async def _discover(database: Database) -> dict[int, list[int]]:
    async with database.maintenance_session() as session:
        rows = (await session.execute(_ATTACHED_TEMP_ROWS_SQL)).mappings().all()
    grouped: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        grouped[int(row["user_id"])].append(int(row["id"]))
    return dict(grouped)


async def _run(apply: bool) -> None:
    settings: Settings = get_settings()
    database = Database(settings.database_url)
    storage = build_file_storage(settings)
    try:
        grouped = await _discover(database)
        total = sum(len(ids) for ids in grouped.values())
        print(f"attached_temp_rows={total} users={sorted(grouped)}")
        if not apply:
            return
        moved = 0
        failures = 0
        for user_id, attachment_ids in grouped.items():
            service = ChatAttachmentService(
                repository=ChatAttachmentRepository(
                    database,
                    user_id=user_id,
                    role="user",
                ),
                storage=storage,
                max_upload_bytes=settings.chat_attachment_max_bytes,
                user_id=user_id,
            )
            for attachment_id in attachment_ids:
                try:
                    await service.promote_attachment(attachment_id)
                except Exception:
                    failures += 1
                    logger.exception(
                        "Could not promote chat attachment attachment_id=%s user_id=%s",
                        attachment_id,
                        user_id,
                    )
                    continue
                moved += 1
                print(f"promoted attachment_id={attachment_id} user_id={user_id}")
        print(f"migration complete: promoted={moved} failed={failures}")
        if failures:
            raise SystemExit(1)
    finally:
        await database.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging(debug=False)
    asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    main()
