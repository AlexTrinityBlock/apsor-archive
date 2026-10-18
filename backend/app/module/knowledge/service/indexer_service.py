"""Shared chunk indexing for files, memories, and summaries."""

import logging

from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.exception.domain_error import EmbeddingProviderError
from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.shared.text.ngram import term_frequencies

logger = logging.getLogger(__name__)


class IndexerService:
    """Persist chunks, n-grams, and optional vectors for any source kind."""

    def __init__(
        self,
        chunk_repository: ChunkRepositoryProtocol,
        embedder: EmbedderProtocol,
    ) -> None:
        self.chunk_repository = chunk_repository
        self.embedder = embedder

    async def _embeddings(self, texts: list[str]) -> list[list[float] | None]:
        if self.embedder.dimension <= 0 or not texts:
            return [None for _text in texts]
        try:
            vectors = await self.embedder.embed(texts)
        except EmbeddingProviderError as exc:
            logger.warning("Embedding provider failed; indexing text only: %s", exc)
            return [None for _text in texts]
        if len(vectors) != len(texts):
            logger.warning(
                "Embedding provider returned %d vectors for %d texts",
                len(vectors),
                len(texts),
            )
            return [None for _text in texts]
        return [vector if vector else None for vector in vectors]

    async def index_chunks(
        self,
        *,
        source_kind: str,
        source_id: int,
        drafts: list[ChunkDraft],
    ) -> int:
        """Index every draft and return the number of chunks written."""
        if not drafts:
            return 0
        embeddings = await self._embeddings([draft.content for draft in drafts])
        for draft, embedding in zip(drafts, embeddings, strict=True):
            chunk = ChunkModel(
                source_kind=source_kind,
                source_id=source_id,
                chunk_index=draft.index,
                content=draft.content,
                char_count=draft.char_count,
                token_count=draft.token_count,
                embedding=embedding,
                embedding_model=self.embedder.model_name if embedding is not None else None,
            )
            await self.chunk_repository.add(chunk)
            await self.chunk_repository.add_ngrams(
                chunk.id,
                dict(term_frequencies(draft.content)),
            )
        return len(drafts)

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
