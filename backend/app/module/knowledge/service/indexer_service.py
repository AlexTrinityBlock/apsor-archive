"""Shared chunk indexing for files, memories, and summaries."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.exception.domain_error import EmbeddingProviderError
from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.shared.text.ngram import term_frequencies

logger = logging.getLogger(__name__)

EmbeddingProgress = Callable[[int, int], Awaitable[None]]
IndexCheckpoint = Callable[[], Awaitable[None]]


class IndexerService:
    """Persist chunks, n-grams, and optional vectors for any source kind.

    Embedding calls run in bounded batches. A shared semaphore caps concurrent
    provider calls when several jobs use the same worker. Provider calls run
    concurrently up to that limit, while chunk persistence, checkpoints, and
    progress updates stay serialized on the caller's event loop because the
    SQLAlchemy session is not concurrency-safe. Transient provider failures get a
    small bounded retry with exponential backoff. Strict callers (the durable
    ingestion worker) surface the error after the retry budget; other callers
    keep the legacy text-only fallback.
    """

    def __init__(
        self,
        chunk_repository: ChunkRepositoryProtocol,
        embedder: EmbedderProtocol,
        *,
        embedding_batch_size: int = 16,
        embedding_concurrency: int = 6,
        embedding_semaphore: asyncio.Semaphore | None = None,
        embedding_max_attempts: int = 3,
        embedding_retry_seconds: float = 0.25,
        fail_on_embedding_error: bool = False,
    ) -> None:
        self.chunk_repository = chunk_repository
        self.embedder = embedder
        self.embedding_batch_size = max(1, embedding_batch_size)
        self.embedding_concurrency = max(1, embedding_concurrency)
        self._embedding_slots = embedding_semaphore or asyncio.Semaphore(
            self.embedding_concurrency
        )
        self.embedding_max_attempts = max(1, embedding_max_attempts)
        self.embedding_retry_seconds = max(0.0, embedding_retry_seconds)
        self.fail_on_embedding_error = fail_on_embedding_error

    def _embedding_failure(self, exc: EmbeddingProviderError) -> None:
        if self.fail_on_embedding_error:
            raise exc
        logger.warning("Embedding provider failed; indexing text only: %s", exc)

    async def _embeddings(self, texts: list[str]) -> list[list[float] | None]:
        if self.embedder.dimension <= 0 or not texts:
            return [None for _text in texts]

        attempt = 1
        while True:
            try:
                async with self._embedding_slots:
                    vectors = await self.embedder.embed(texts)
                if len(vectors) != len(texts):
                    raise EmbeddingProviderError(
                        f"Embedding provider returned {len(vectors)} vectors for "
                        f"{len(texts)} texts"
                    )
            except EmbeddingProviderError as exc:
                if attempt >= self.embedding_max_attempts:
                    self._embedding_failure(exc)
                    return [None for _text in texts]
                delay = self.embedding_retry_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Embedding attempt %d/%d failed; retrying in %.2fs: %s",
                    attempt,
                    self.embedding_max_attempts,
                    delay,
                    exc,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                attempt += 1
                continue
            return [vector if vector else None for vector in vectors]

    async def index_chunks(
        self,
        *,
        source_kind: str,
        source_id: int,
        drafts: list[ChunkDraft],
        is_current: bool = True,
        progress: EmbeddingProgress | None = None,
        checkpoint: IndexCheckpoint | None = None,
    ) -> int:
        """Index every draft in bounded batches and return the chunk count.

        ``is_current`` is false while a durable job stages a new file version;
        the publish step flips all staged chunks visible at once. ``progress``
        receives ``(processed, total)`` after each batch so the worker can keep
        the job row's counter and progress bar moving without per-chunk writes.
        ``checkpoint`` commits the worker's transaction after each batch, which
        keeps a long embedding pass from holding one database transaction open.
        """
        total = len(drafts)
        if total == 0:
            return 0

        batches = [
            drafts[start : start + self.embedding_batch_size]
            for start in range(0, total, self.embedding_batch_size)
        ]
        tasks = {
            asyncio.create_task(
                self._embeddings([draft.content for draft in batch])
            ): batch
            for batch in batches
        }
        pending = set(tasks)
        processed = 0
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    batch = tasks[task]
                    embeddings = task.result()
                    for draft, embedding in zip(batch, embeddings, strict=True):
                        chunk = ChunkModel(
                            source_kind=source_kind,
                            source_id=source_id,
                            chunk_index=draft.index,
                            content=draft.content,
                            char_count=draft.char_count,
                            token_count=draft.token_count,
                            embedding=embedding,
                            embedding_model=(
                                self.embedder.model_name
                                if embedding is not None
                                else None
                            ),
                            is_current=is_current,
                        )
                        await self.chunk_repository.add(chunk)
                        await self.chunk_repository.add_ngrams(
                            chunk.id,
                            dict(term_frequencies(draft.content)),
                        )
                    processed += len(batch)
                    if checkpoint is not None:
                        await checkpoint()
                    if progress is not None:
                        await progress(processed, total)
        except BaseException:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            raise
        return total

    async def index_single(
        self,
        *,
        source_kind: str,
        source_id: int,
        content: str,
    ) -> int:
        """Index a memory or summary as one chunk."""
        draft = ChunkDraft(
            index=1,
            content=content,
            char_count=len(content),
            token_count=sum(term_frequencies(content).values()),
        )
        return await self.index_chunks(
            source_kind=source_kind,
            source_id=source_id,
            drafts=[draft],
        )
