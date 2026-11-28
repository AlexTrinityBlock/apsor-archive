"""API-side status and retry nudge for the worker's embedding backfill.

The backfill runs in the dedicated worker process; the API reaches it through
the cache. Counts come from a maintenance query that reads only ``user_id`` and
aggregates, never chunk content, the same privilege the embedding reindex uses
to enumerate owners.
"""

import logging
from datetime import datetime

from sqlalchemy import text

from app.infrastructure.database.session import Database
from app.module.knowledge.domain.embedding_backfill_domain import (
    MAX_EMBEDDING_FAILURES,
    utc_now,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.schema.system_schema import EmbeddingBackfillStatusSchema
from app.module.knowledge.service.embedding_backfill import (
    NUDGE_CACHE_KEY,
    NUDGE_TTL_SECONDS,
    STATUS_CACHE_KEY,
)

logger = logging.getLogger(__name__)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class EmbeddingBackfillStatusService:
    """Report pending embeddings and ask the worker to retry now."""

    def __init__(
        self,
        database: Database,
        cache: CacheProtocol,
        *,
        max_failures: int = MAX_EMBEDDING_FAILURES,
    ) -> None:
        self.database = database
        self.cache = cache
        self.max_failures = max_failures

    async def status(self) -> EmbeddingBackfillStatusSchema:
        async with self.database.maintenance_session() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                            SELECT
                              count(*) FILTER (
                                WHERE embedding_failures < :max_failures
                              ) AS pending_chunks,
                              count(DISTINCT user_id) FILTER (
                                WHERE embedding_failures < :max_failures
                              ) AS pending_accounts,
                              count(*) FILTER (
                                WHERE embedding_failures >= :max_failures
                              ) AS abandoned_chunks
                            FROM chunk
                            WHERE embedding IS NULL
                            """
                        ),
                        {"max_failures": self.max_failures},
                    )
                )
                .mappings()
                .one()
            )
        published = await self._published()
        error_code = published.get("last_error_code")
        return EmbeddingBackfillStatusSchema(
            pending_chunks=int(row["pending_chunks"] or 0),
            pending_accounts=int(row["pending_accounts"] or 0),
            abandoned_chunks=int(row["abandoned_chunks"] or 0),
            worker_state=str(published.get("state") or "unknown"),
            resume_at=_parse_time(published.get("resume_at")),
            last_error_code=error_code if isinstance(error_code, str) else None,
            allowance_blocked_accounts=_int(published.get("allowance_blocked_accounts")),
            updated_at=_parse_time(published.get("updated_at")),
        )

    async def request_retry(self) -> EmbeddingBackfillStatusSchema:
        """Ask the worker to close its breaker and retry on its next cycle."""
        try:
            await self.cache.set_json(
                NUDGE_CACHE_KEY,
                utc_now().timestamp(),
                NUDGE_TTL_SECONDS,
            )
        except Exception:  # pragma: no cover - the cache is disposable.
            logger.warning("could not publish the embedding backfill retry request")
        return await self.status()

    async def _published(self) -> dict[str, object]:
        try:
            value = await self.cache.get_json(STATUS_CACHE_KEY)
        except Exception:  # pragma: no cover - the cache is disposable.
            return {}
        return value if isinstance(value, dict) else {}


__all__ = ["EmbeddingBackfillStatusService"]
