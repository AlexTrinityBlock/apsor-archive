"""Choose the librarian's own memories to offer beside a search.

The recall is scored against the search query plus the top archive excerpts:

- **lexical**: theme overlap through the multilingual vocabulary, plus shared
  words (Latin words and CJK bigrams);
- **semantic**: cosine similarity with the account's configured embedder, when
  it has a dimension and the account's embedding allowance permits it.

Fragment vectors are cached in process memory by ``(model, sha256(text))``, so
repeated searches embed only the query. Any embedding failure falls back to the
lexical score. Locked tiers are never offered.
"""

import hashlib
import logging
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

from app.module.companion.domain.story_domain import (
    MAX_RECALLED_FRAGMENTS,
    LoreFragment,
    LoreVocabulary,
    StoryLocale,
    cosine,
    is_self_query,
    lexical_score,
    select_fragments,
)
from app.module.companion.exception.domain_error import CompanionRefNotFoundError
from app.module.companion.protocol.companion_story_protocol import (
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.service.companion_story_service import (
    CompanionStoryService,
    StoryTarget,
)
from app.module.companion.service.preset_lore_catalog import load_presets, load_vocabulary

logger = logging.getLogger(__name__)

_CONTEXT_CHARS = 1200
_VECTOR_CACHE_SIZE = 4096
_vector_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()


@dataclass(frozen=True)
class RecalledLore:
    """One fragment offered to the model for this search."""

    id: str
    text: str
    tier: str
    score: float


def _cache_key(model_name: str, text: str) -> tuple[str, str]:
    return model_name, hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(key: tuple[str, str]) -> list[float] | None:
    vector = _vector_cache.get(key)
    if vector is not None:
        _vector_cache.move_to_end(key)
    return vector


def _cache_put(key: tuple[str, str], vector: list[float]) -> None:
    _vector_cache[key] = vector
    _vector_cache.move_to_end(key)
    while len(_vector_cache) > _VECTOR_CACHE_SIZE:
        _vector_cache.popitem(last=False)


class CompanionLoreRecall:
    """Select up to two unlocked fragments of one companion for one search."""

    def __init__(
        self,
        *,
        stories: CompanionStoryService,
        companion_ref: str,
        locale: StoryLocale,
        embedder: LoreEmbedderProtocol | None = None,
        quota: LoreEmbeddingQuotaProtocol | None = None,
        vocabulary: LoreVocabulary | None = None,
    ) -> None:
        self.stories = stories
        self.companion_ref = companion_ref
        self.locale = locale
        self.embedder = embedder
        self.quota = quota
        self.vocabulary = vocabulary or load_vocabulary()

    async def recall(
        self,
        query: str,
        context: Sequence[str] = (),
        *,
        limit: int = MAX_RECALLED_FRAGMENTS,
    ) -> list[RecalledLore]:
        """Return the fragments worth offering; empty when nothing fits."""
        try:
            target = await self.stories.resolve(self.companion_ref)
        except CompanionRefNotFoundError:  # a deleted custom companion has no lore
            return []
        fragments = await self.stories.fragments(target, self.locale)
        if not fragments:
            return []
        bond = await self.stories.bond(target.ref)
        unlocked = bond.unlocked_tiers()
        candidates = [fragment for fragment in fragments if fragment.tier in unlocked]
        if not candidates:
            return []
        scoring_text = " ".join([query, *context])[: _CONTEXT_CHARS + len(query)]
        lexical = {
            fragment.key: lexical_score(scoring_text, fragment, self.vocabulary)
            for fragment in candidates
        }
        semantic = await self._semantic(scoring_text, candidates)
        chosen = select_fragments(
            fragments=candidates,
            unlocked=unlocked,
            lexical=lexical,
            semantic=semantic,
            self_query=is_self_query(query, self._names(target)),
            limit=limit,
        )
        return [
            RecalledLore(
                id=item.fragment.key,
                text=item.fragment.text,
                tier=item.fragment.tier,
                score=item.score,
            )
            for item in chosen
        ]

    def _names(self, target: StoryTarget) -> list[str]:
        """Return the librarian's own name and every preset librarian's name."""
        names = {target.name}
        for locale in ("en", self.locale):
            names.update(preset.name for preset in load_presets(locale).values())
        return sorted(name for name in names if name)

    async def _semantic(
        self,
        text: str,
        fragments: Sequence[LoreFragment],
    ) -> dict[str, float] | None:
        embedder = self.embedder
        if embedder is None or embedder.dimension <= 0:
            return None
        model = embedder.model_name
        missing = [
            fragment
            for fragment in fragments
            if _cache_get(_cache_key(model, fragment.text)) is None
        ]
        batch = [text, *(fragment.text for fragment in missing)]
        characters = sum(len(item) for item in batch)
        try:
            if self.quota is not None and not await self.quota.embedding_allowed(characters):
                return None
            vectors = await embedder.embed(batch)
            if self.quota is not None:
                await self.quota.record_embedding(characters)
        except Exception:
            logger.warning("lore recall embedding failed; using lexical scores only")
            return None
        if len(vectors) != len(batch):
            return None
        query_vector = vectors[0]
        for fragment, vector in zip(missing, vectors[1:], strict=True):
            _cache_put(_cache_key(model, fragment.text), vector)
        scores: dict[str, float] = {}
        for fragment in fragments:
            cached = _cache_get(_cache_key(model, fragment.text))
            if cached is not None:
                scores[fragment.key] = cosine(query_vector, cached)
        return scores


__all__ = ["CompanionLoreRecall", "RecalledLore"]
