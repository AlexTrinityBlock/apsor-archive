"""Worker-only loop that fills in chunk embeddings left pending.

Ingestion, memories, summaries, markdown edits, and the conversation-history
indexer all store their text and n-grams even when the embedding provider is
out of credits, unreachable, rejects the key, or the account allowance is spent.
Those rows keep a NULL ``embedding`` and stay searchable by keywords. This loop
is the other half of that promise: it embeds every pending row once the
provider and the account allow it, so nothing is silently lost.

Discovery runs in a maintenance session that returns owner ids only, never
chunk content. Every read and write of a chunk then happens in that owner's
``user_session`` through an owner-scoped repository, in short independently
committed batches.

Failures are classified by :mod:`embedding_backfill_domain`:

* systemic (billing, quota, auth, rate limit, outage, network) trips a global
  circuit breaker with exponential backoff up to 30 minutes, and never counts
  against a row;
* per-chunk (HTTP 400/413/422) is retried one chunk at a time and counted on the
  row, which stops being retried after ``MAX_EMBEDDING_FAILURES``.

The breaker closes at once when the provider configuration changes (the
embedding chain fingerprint differs after a refresh) or when root asks for a
retry from the system notices panel; that nudge travels through the cache so
the API process can reach the worker. The loop publishes a small status record
in the cache for the root status endpoint.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.knowledge.domain.embedding_backfill_domain import (
    MAX_EMBEDDING_FAILURES,
    CircuitBreaker,
    failure_code,
    is_per_chunk_failure,
    utc_now,
)
from app.module.knowledge.exception.domain_error import EmbeddingProviderError
from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.embedding_quota_protocol import EmbeddingQuotaProtocol
from app.module.knowledge.service.cache_keys import user_version_scope

logger = logging.getLogger(__name__)

EMBEDDING_BACKFILL_BATCH_SIZE = 32
EMBEDDING_BACKFILL_INTERVAL_SECONDS = 30
STATUS_CACHE_KEY = "apsor:embedding-backfill:status"
NUDGE_CACHE_KEY = "apsor:embedding-backfill:nudge"
STATUS_TTL_SECONDS = 24 * 60 * 60
NUDGE_TTL_SECONDS = 24 * 60 * 60

ROLE_USER = "user"

ChunkRepositoryFactory = Callable[[AsyncSession, int], ChunkRepositoryProtocol]
QuotaFactory = Callable[[int], EmbeddingQuotaProtocol]
EmbedderRefresh = Callable[[], Awaitable[EmbedderProtocol]]


@dataclass
class EmbeddingBackfillBatch:
    """Outcome of one backfill cycle."""

    owners: int = 0
    embedded: int = 0
    failed_chunks: int = 0
    skipped_owners: list[int] = field(default_factory=list)
    breaker_open: bool = False
    disabled: bool = False


class EmbeddingBackfill:
    """Embed pending chunks for every account, resuming after outages."""

    def __init__(
        self,
        *,
        database: Database,
        embedder_refresh: EmbedderRefresh,
        chunk_repository_factory: ChunkRepositoryFactory,
        quota_factory: QuotaFactory,
        cache: CacheProtocol | None = None,
        fingerprint: Callable[[], object] | None = None,
        batch_size: int = EMBEDDING_BACKFILL_BATCH_SIZE,
        interval_seconds: float = EMBEDDING_BACKFILL_INTERVAL_SECONDS,
        max_failures: int = MAX_EMBEDDING_FAILURES,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.database = database
        self.embedder_refresh = embedder_refresh
        self.chunk_repository_factory = chunk_repository_factory
        self.quota_factory = quota_factory
        self.cache = cache
        self.fingerprint = fingerprint
        self.batch_size = max(1, batch_size)
        self.interval_seconds = max(0.0, interval_seconds)
        self.max_failures = max(1, max_failures)
        self.now = now
        self.breaker = CircuitBreaker()
        self._last_fingerprint: object | None = None
        self._last_nudge: float | None = None
        self.last_batch = EmbeddingBackfillBatch()

    # ------------------------------------------------------------------
    # Loop control
    # ------------------------------------------------------------------

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Backfill continuously; sleep when idle or while the breaker is open."""
        logger.info("embedding backfill started")
        while stop_event is None or not stop_event.is_set():
            try:
                batch = await self.run_once()
            except Exception:
                logger.exception("embedding backfill cycle failed")
                batch = EmbeddingBackfillBatch()
            if batch.embedded and not batch.breaker_open:
                # More may be waiting; yield and continue without sleeping.
                await asyncio.sleep(0)
                continue
            await self._sleep(stop_event)

    async def _sleep(self, stop_event: asyncio.Event | None) -> None:
        delay = self.interval_seconds
        if delay <= 0:
            await asyncio.sleep(0)
            return
        if stop_event is None:
            await asyncio.sleep(delay)
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def run_once(self) -> EmbeddingBackfillBatch:
        """Run one cycle: refresh the provider, then embed one batch per owner."""
        batch = EmbeddingBackfillBatch()
        embedder = await self.embedder_refresh()
        await self._observe_resets()
        if embedder.dimension <= 0:
            batch.disabled = True
            await self._publish(batch)
            self.last_batch = batch
            return batch
        if self.breaker.is_open(self.now()):
            batch.breaker_open = True
            await self._publish(batch)
            self.last_batch = batch
            return batch

        owner_ids = await self.pending_owner_ids()
        for owner_id in owner_ids:
            if self.breaker.is_open(self.now()):
                batch.breaker_open = True
                break
            await self._process_owner(owner_id, embedder, batch)
        batch.owners = len(owner_ids)
        if batch.embedded and not batch.breaker_open:
            self.breaker.reset()
        await self._publish(batch)
        self.last_batch = batch
        return batch

    async def drain(self, *, max_cycles: int = 1000) -> int:
        """Run cycles until nothing more can be embedded now (tests, CLI)."""
        total = 0
        for _cycle in range(max_cycles):
            batch = await self.run_once()
            total += batch.embedded
            if not batch.embedded or batch.breaker_open or batch.disabled:
                return total
        return total

    async def retry_now(self) -> None:
        """Close the breaker in this process (the worker's own nudge path)."""
        self.breaker.reset()

    # ------------------------------------------------------------------
    # Discovery and processing
    # ------------------------------------------------------------------

    async def pending_owner_ids(self) -> list[int]:
        """Return owners with pending rows; reads ids only, never content."""
        async with self.database.maintenance_session() as session:
            rows = await session.execute(
                text(
                    """
                    SELECT DISTINCT user_id
                    FROM chunk
                    WHERE embedding IS NULL
                      AND embedding_failures < :max_failures
                    ORDER BY user_id
                    """
                ),
                {"max_failures": self.max_failures},
            )
            return [int(row[0]) for row in rows.all()]

    async def _process_owner(
        self,
        owner_id: int,
        embedder: EmbedderProtocol,
        batch: EmbeddingBackfillBatch,
    ) -> None:
        quota = self.quota_factory(owner_id)
        async with self.database.user_session(owner_id, ROLE_USER) as session:
            repository = self.chunk_repository_factory(session, owner_id)
            chunks = await repository.list_pending_embeddings(
                after_id=0,
                limit=self.batch_size,
                max_failures=self.max_failures,
            )
            if not chunks:
                return
            characters = sum(max(0, chunk.char_count) for chunk in chunks)
            if not await quota.embedding_allowed(characters):
                # The account allowance is spent; retry this owner on a later
                # cycle (root may raise the grant, or the period may reset).
                batch.skipped_owners.append(owner_id)
                return
            embedded, failed = await self._embed_chunks(repository, embedder, chunks)
        if embedded:
            embedded_chars = sum(max(0, chunk.char_count) for chunk in embedded)
            await quota.record_embedding(embedded_chars)
            await self._bump_owner_index(owner_id)
        batch.embedded += len(embedded)
        batch.failed_chunks += failed

    async def _embed_chunks(
        self,
        repository: ChunkRepositoryProtocol,
        embedder: EmbedderProtocol,
        chunks: list[ChunkModel],
    ) -> tuple[list[ChunkModel], int]:
        """Embed a batch; isolate per-chunk failures; trip on systemic ones."""
        try:
            vectors = await self._embed([chunk.content for chunk in chunks], embedder)
        except EmbeddingProviderError as exc:
            if not is_per_chunk_failure(exc.status_code):
                self._trip(exc)
                return [], 0
            return await self._embed_one_by_one(repository, embedder, chunks)
        for chunk, vector in zip(chunks, vectors, strict=True):
            await repository.update_embedding(chunk.id, vector, embedder.model_name)
        return list(chunks), 0

    async def _embed_one_by_one(
        self,
        repository: ChunkRepositoryProtocol,
        embedder: EmbedderProtocol,
        chunks: list[ChunkModel],
    ) -> tuple[list[ChunkModel], int]:
        embedded: list[ChunkModel] = []
        poisoned: list[int] = []
        for chunk in chunks:
            try:
                vectors = await self._embed([chunk.content], embedder)
            except EmbeddingProviderError as exc:
                if not is_per_chunk_failure(exc.status_code):
                    self._trip(exc)
                    break
                poisoned.append(chunk.id)
                continue
            await repository.update_embedding(chunk.id, vectors[0], embedder.model_name)
            embedded.append(chunk)
        if poisoned:
            await repository.record_embedding_failure(poisoned)
            logger.warning(
                "embedding backfill could not embed %d chunk(s); they stay "
                "keyword-searchable and are retried up to %d times",
                len(poisoned),
                self.max_failures,
            )
        return embedded, len(poisoned)

    @staticmethod
    async def _embed(texts: list[str], embedder: EmbedderProtocol) -> list[list[float]]:
        vectors = await embedder.embed(texts)
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise EmbeddingProviderError(
                f"The provider returned {len(vectors)} vectors for {len(texts)} texts."
            )
        return vectors

    def _trip(self, exc: EmbeddingProviderError) -> None:
        code = failure_code(exc.status_code)
        until = self.breaker.trip(code, self.now())
        logger.warning(
            "embedding backfill paused after a provider failure code=%s "
            "resume_at=%s; pending chunks keep keyword search",
            code,
            until.isoformat(),
        )

    async def _bump_owner_index(self, owner_id: int) -> None:
        if self.cache is None:
            return
        try:
            await self.cache.bump_version(user_version_scope(owner_id))
        except Exception:  # pragma: no cover - the cache is disposable.
            logger.debug("could not bump the search cache version after backfill")

    # ------------------------------------------------------------------
    # Resets and status
    # ------------------------------------------------------------------

    async def _observe_resets(self) -> None:
        """Close the breaker on a provider change or a root retry nudge."""
        if self.fingerprint is not None:
            current = self.fingerprint()
            if self._last_fingerprint is not None and current != self._last_fingerprint:
                if self.breaker.open_until is not None:
                    logger.info("embedding provider changed; resuming the backfill")
                self.breaker.reset()
            self._last_fingerprint = current
        nudge = await self._read_nudge()
        if nudge is not None and nudge != self._last_nudge:
            if self._last_nudge is not None or self.breaker.open_until is not None:
                logger.info("embedding backfill retry requested; resuming now")
                self.breaker.reset()
            self._last_nudge = nudge

    async def _read_nudge(self) -> float | None:
        if self.cache is None:
            return None
        try:
            value = await self.cache.get_json(NUDGE_CACHE_KEY)
        except Exception:  # pragma: no cover - the cache is disposable.
            return None
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return None

    async def _publish(self, batch: EmbeddingBackfillBatch) -> None:
        if self.cache is None:
            return
        now = self.now()
        if batch.disabled:
            state = "disabled"
        elif self.breaker.is_open(now):
            state = "paused"
        elif batch.embedded:
            state = "running"
        else:
            state = "idle"
        payload: dict[str, object] = {
            "state": state,
            "resume_at": (
                self.breaker.open_until.isoformat()
                if self.breaker.open_until is not None and self.breaker.is_open(now)
                else None
            ),
            "last_error_code": self.breaker.last_error_code,
            "consecutive_failures": self.breaker.consecutive_failures,
            "embedded_last_cycle": batch.embedded,
            "allowance_blocked_accounts": len(batch.skipped_owners),
            "updated_at": now.isoformat(),
        }
        try:
            await self.cache.set_json(STATUS_CACHE_KEY, payload, STATUS_TTL_SECONDS)
        except Exception:  # pragma: no cover - the cache is disposable.
            logger.debug("could not publish the embedding backfill status")


__all__ = [
    "EMBEDDING_BACKFILL_BATCH_SIZE",
    "EMBEDDING_BACKFILL_INTERVAL_SECONDS",
    "NUDGE_CACHE_KEY",
    "STATUS_CACHE_KEY",
    "EmbeddingBackfill",
    "EmbeddingBackfillBatch",
]
