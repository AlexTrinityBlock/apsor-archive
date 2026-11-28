"""Choose the librarian's own memories to offer, and pace its story.

There are three ways a fragment reaches the model, and none needs a keyword:

- **Topical recall** beside a search: cosine similarity between the fragment
  and the query plus the top archive excerpts, using the account's embedder.
  Only a semantic embedder counts; without one, topical recall offers nothing.
  Untold fragments are preferred and each earlier telling lowers a fragment.
- **Self queries** ("tell me about yourself", a librarian's name, "your past"):
  the next untold fragments of the arc, the most relevant of a small window
  first (semantic when available, otherwise light word overlap).
- **Story moments** at the start of a run, every few completed runs: the next
  untold fragment of the arc, whatever the user talks about, so a person whose
  life circles a few topics still hears the whole story in time.

Every offer is counted in the progress table with its source. Locked tiers are
never offered. Thresholds, cadence, phrases, and guidance come from the story
config provider, never from module constants.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.module.companion.domain.recall_domain import (
    RecalledFragment,
    cosine,
    is_self_query,
    is_semantic_embedder,
    lexical_overlap,
    next_untold,
    rank_self_query,
    rank_topical,
    story_moment_due,
)
from app.module.companion.domain.story_domain import (
    TEMPLATE_LORE_GUIDANCE,
    TEMPLATE_STORY_MOMENT_GUIDANCE,
    CompanionRuntimeConfig,
    CompanionStoryConfig,
    LoreFragment,
    StoryLocale,
)
from app.module.companion.exception.domain_error import CompanionRefNotFoundError
from app.module.companion.protocol.companion_story_protocol import (
    CompanionStoryConfigProviderProtocol,
    LoreEmbedderProtocol,
    LoreEmbeddingQuotaProtocol,
)
from app.module.companion.service.companion_story_service import (
    CompanionStoryService,
    StoryTarget,
)
from app.module.companion.service.lore_vectors import LoreVectorStore

logger = logging.getLogger(__name__)


def _lore_guidance(config: CompanionStoryConfig) -> str:
    """Return the configured topical/self guidance (template first)."""
    if isinstance(config, CompanionRuntimeConfig):
        return config.template(TEMPLATE_LORE_GUIDANCE, config.lore_guidance)
    return config.lore_guidance


def _story_moment_guidance(config: CompanionStoryConfig) -> str:
    """Return the configured story-moment guidance (template first)."""
    if isinstance(config, CompanionRuntimeConfig):
        return config.template(TEMPLATE_STORY_MOMENT_GUIDANCE, config.story_moment_guidance)
    return config.story_moment_guidance


_CONTEXT_CHARS = 1200


RecallMoment = Literal["story", "topical", "self"]


@dataclass(frozen=True)
class RecalledLore:
    """One fragment offered to the model."""

    id: str
    text: str
    tier: str
    score: float
    # The configured guidance the model reads with this memory.
    guidance: str = ""
    # How the fragment surfaced: a paced story moment, a topical match, or an
    # answer to a question about the librarian itself.
    moment: RecallMoment = "topical"


def _offered(
    chosen: Sequence[RecalledFragment],
    guidance: str,
    moment: RecallMoment,
) -> list[RecalledLore]:
    return [
        RecalledLore(
            id=item.fragment.key,
            text=item.fragment.text,
            tier=item.fragment.tier,
            score=item.score,
            guidance=guidance,
            moment=moment,
        )
        for item in chosen
    ]


class CompanionLoreRecall:
    """Offer one companion's lore beside searches and as paced story moments."""

    def __init__(
        self,
        *,
        stories: CompanionStoryService,
        companion_ref: str,
        locale: StoryLocale,
        embedder: LoreEmbedderProtocol | None = None,
        quota: LoreEmbeddingQuotaProtocol | None = None,
        vectors: LoreVectorStore | None = None,
        config: CompanionStoryConfigProviderProtocol,
    ) -> None:
        self.stories = stories
        self.companion_ref = companion_ref
        self.locale = locale
        self.embedder = embedder
        self.quota = quota
        self.vectors = vectors or LoreVectorStore()
        self.config = config

    async def recall(
        self,
        query: str,
        context: Sequence[str] = (),
        *,
        limit: int | None = None,
        exclude: frozenset[str] = frozenset(),
        allow_self_query: bool = True,
        allow_topical: bool = True,
    ) -> list[RecalledLore]:
        """Return the fragments worth offering for one input.

        ``exclude`` lists fragment ids already offered in this run. A self
        query is recognized only in ``query`` (the person's own words) and
        only when ``allow_self_query``; otherwise ranking is topical, and
        ``allow_topical=False`` turns topical recall off (a user message offers
        only self-query answers or story moments, never topical asides).
        """
        config = await self.config.load(self.stories.user_id)
        size = config.max_recalled_fragments if limit is None else limit
        if size <= 0:
            return []
        self_query = allow_self_query and bool(query.strip())
        if not allow_topical and not self_query:
            return []
        try:
            target = await self.stories.resolve(self.companion_ref)
        except CompanionRefNotFoundError:  # a deleted custom companion has no lore
            return []
        fragments = await self.stories.fragments(target, self.locale)
        if not fragments:
            return []
        unlocked = (await self.stories.bond(target.ref)).unlocked_tiers(config)
        candidates = [
            fragment
            for fragment in fragments
            if fragment.tier in unlocked and fragment.key not in exclude
        ]
        if not candidates:
            return []
        told = await self.stories.told(target.ref)
        scoring_text = " ".join(part for part in [query, *context] if part)
        scoring_text = scoring_text[: _CONTEXT_CHARS + len(query)]
        moment: RecallMoment
        if self_query and is_self_query(query, await self._names(target), config):
            semantic = await self._semantic(scoring_text, candidates)
            relevance = (
                semantic
                if semantic is not None
                else {fragment.key: lexical_overlap(query, fragment) for fragment in candidates}
            )
            chosen = rank_self_query(
                candidates, unlocked, told, relevance, limit=size, config=config
            )
            source = "self_query"
            moment = "self"
        elif not allow_topical:
            return []
        else:
            semantic = await self._semantic(scoring_text, candidates)
            chosen = rank_topical(
                candidates, unlocked, semantic, told, limit=size, config=config
            )
            source = "topical"
            moment = "topical"
        await self.stories.record_told(
            target.ref,
            [item.fragment.key for item in chosen],
            source,
        )
        return _offered(chosen, _lore_guidance(config), moment)

    async def story_moment(self, *, exclude: frozenset[str] = frozenset()) -> RecalledLore | None:
        """Return the next untold fragment when a story moment is due, else ``None``.

        A due moment is counted at once, so the next one waits for a few more
        completed runs even if the model chose to keep this one for later.
        """
        try:
            target = await self.stories.resolve(self.companion_ref)
        except CompanionRefNotFoundError:
            return None
        config = await self.config.load(self.stories.user_id)
        bond = await self.stories.bond(target.ref)
        if not story_moment_due(bond, config):
            return None
        fragments = [
            fragment
            for fragment in await self.stories.fragments(target, self.locale)
            if fragment.key not in exclude
        ]
        told = await self.stories.told(target.ref)
        upcoming = next_untold(fragments, bond.unlocked_tiers(config), told, limit=1)
        if not upcoming:
            return None
        fragment = upcoming[0]
        await self.stories.record_told(target.ref, [fragment.key], "story_moment")
        await self.stories.mark_story_moment(target.ref, bond.completed_runs)
        return RecalledLore(
            id=fragment.key,
            text=fragment.text,
            tier=fragment.tier,
            score=0.0,
            guidance=_story_moment_guidance(config),
            moment="story",
        )

    async def _names(self, target: StoryTarget) -> list[str]:
        """Return the librarian's own name and every preset librarian's name."""
        names = {target.name, *await self.stories.preset_names(self.locale)}
        return sorted(name for name in names if name)

    async def _semantic(
        self,
        text: str,
        fragments: Sequence[LoreFragment],
    ) -> dict[str, float] | None:
        """Return cosine similarities, or ``None`` without a semantic embedder."""
        embedder = self.embedder
        if embedder is None or not is_semantic_embedder(embedder.model_name, embedder.dimension):
            return None
        model = embedder.model_name
        known: dict[str, list[float]] = {}
        missing: list[LoreFragment] = []
        for fragment in fragments:
            vector = await self.vectors.get(model, fragment.text)
            if vector is None:
                missing.append(fragment)
            else:
                known[fragment.key] = vector
        batch = [text, *(fragment.text for fragment in missing)]
        characters = sum(len(item) for item in batch)
        try:
            if self.quota is not None and not await self.quota.embedding_allowed(characters):
                return None
            vectors = await embedder.embed(batch)
            if self.quota is not None:
                await self.quota.record_embedding(characters)
        except Exception:
            logger.warning("lore recall embedding failed; offering no topical lore")
            return None
        if len(vectors) != len(batch):
            return None
        query_vector = vectors[0]
        for fragment, vector in zip(missing, vectors[1:], strict=True):
            known[fragment.key] = vector
            await self.vectors.put(model, fragment.text, vector)
        return {key: cosine(query_vector, vector) for key, vector in known.items()}


__all__ = ["CompanionLoreRecall", "RecallMoment", "RecalledLore"]
