"""Render missing WebP thumbnails for existing files.

The dedicated worker already backfills thumbnails in the background. Use this
one-off command to finish the work immediately or to regenerate thumbnails
after a renderer change:

    uv run python -m script.backfill_thumbnails --dry-run
    uv run python -m script.backfill_thumbnails --apply [--user-id N] [--regenerate]

``--apply`` reads every candidate original once from its storage backend
(local disk or R2). It is safe to re-run: files that already have a current
thumbnail are skipped unless ``--regenerate`` is given. Output is counts only.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from starlette.datastructures import State

from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.cache.resilient_cache import build_cache
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.database.session import Database, system_session
from app.infrastructure.files.storage_factory import build_file_storage
from app.infrastructure.logger.logging import configure_logging
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.knowledge.dependencies import build_thumbnail_backfill
from app.module.knowledge.repository.provider_config_repository import (
    ProviderConfigRepository,
)
from app.module.knowledge.service.provider_error_notice_service import (
    ProviderErrorNoticeService,
)


@dataclass(frozen=True)
class _Arguments:
    apply: bool
    user_id: int | None
    regenerate: bool


def _parse_args(argv: Sequence[str] | None) -> _Arguments:
    parser = argparse.ArgumentParser(description="Backfill WebP file thumbnails.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Count candidates only.")
    mode.add_argument("--apply", action="store_true", help="Render and store thumbnails.")
    parser.add_argument("--user-id", type=int, default=None, help="Limit to one account.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Re-render thumbnails that already exist.",
    )
    arguments = parser.parse_args(argv)
    return _Arguments(
        apply=bool(arguments.apply),
        user_id=arguments.user_id,
        regenerate=bool(arguments.regenerate),
    )


async def _run(arguments: _Arguments) -> None:
    settings: Settings = get_settings()
    database = Database(settings.database_url)
    cache = build_cache(settings.cache_url)
    try:
        cipher = SecretCipher.from_settings(settings)
        notice_service = ProviderErrorNoticeService(database.session_factory)
        runtime = AiRuntime(
            builder=ProviderFactory(settings),
            cipher=cipher,
            defaults=provider_defaults_from_settings(settings),
            reporter=notice_service.report,
        )
        async with system_session(database.session_factory) as session:
            await runtime.reload(ProviderConfigRepository(session))

        state = State()
        state.settings = settings
        state.db = database
        state.cache = cache
        state.storage = build_file_storage(settings)
        state.secret_cipher = cipher
        state.ai_runtime = runtime
        state.provider_notice_service = notice_service

        backfill = build_thumbnail_backfill(
            state,
            database,
            user_id=arguments.user_id,
            regenerate=arguments.regenerate,
        )
        if not arguments.apply:
            print(f"thumbnail_candidates={await backfill.count_candidates()}")
            return
        processed = await backfill.drain()
        print(f"thumbnails_processed={processed}")
    finally:
        await cache.close()
        await database.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging(debug=False)
    asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    main()
