"""Pure recall and pacing rules for companion lore.

Ranking (topical, self query), story-moment cadence, arc order, and the small
lexical/vector helpers they need. Every function takes the live
:class:`CompanionStoryConfig` from the config provider instead of reading
module constants, so root administration can tune them.
"""

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.module.companion.domain.story_domain import (
    LORE_WEIGHTS,
    Bond,
    CompanionStoryConfig,
    StoryItem,
    ToldRecord,
)

_LATIN_WORD = re.compile(r"[a-z][a-z']{2,}")
_CJK_RUN = re.compile(r"[㐀-鿿豈-﫿]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "was",
        "were",
        "are",
        "you",
        "your",
        "his",
        "her",
        "they",
        "them",
        "but",
        "not",
        "have",
        "has",
        "had",
        "one",
        "all",
        "what",
        "when",
        "who",
        "how",
        "she",
        "him",
        "its",
        "into",
        "out",
        "our",
        "about",
        "would",
        "there",
        "been",
        "only",
        "still",
    }
)


@dataclass(frozen=True)
class RecalledFragment:
    """A fragment chosen for one search, with its relevance score."""

    fragment: StoryItem
    score: float


def tokens(text: str) -> set[str]:
    """Return lexical tokens: Latin words (no stopwords) and CJK bigrams."""
    lowered = text.lower()
    found = {word for word in _LATIN_WORD.findall(lowered) if word not in _STOPWORDS}
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            found.add(run)
        found.update(run[index : index + 2] for index in range(len(run) - 1))
    return found


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the cosine similarity of two equal-length vectors (0 when invalid)."""
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def is_semantic_embedder(model_name: str, dimension: int) -> bool:
    """Return whether an embedder measures meaning (the offline hash does not)."""
    return dimension > 0 and bool(model_name) and not model_name.startswith("apsor-hash")


def is_self_query(
    query: str,
    names: Iterable[str],
    config: CompanionStoryConfig,
) -> bool:
    """Return whether ``query`` explicitly asks about the librarian or its kin."""
    settings = config
    lowered = query.lower()
    if any(phrase and phrase in lowered for phrase in settings.self_query_phrases):
        return True
    for term in settings.self_canon_terms:
        if not term:
            continue
        if f"your {term}" in lowered or f"你的{term}" in lowered:
            return True
    for name in names:
        if not name:
            continue
        needle = name.lower()
        if re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", lowered):
            return True
    return False


def lexical_overlap(query: str, fragment: StoryItem) -> float:
    """Return a light word-overlap score used only to order a self query."""
    query_tokens = tokens(query)
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & tokens(fragment.text))
    return min(1.0, overlap / 4)


def arc_order(fragments: Iterable[StoryItem]) -> list[StoryItem]:
    """Return fragments in story order: everyday, past, heart; then by id."""
    rank = {weight: index for index, weight in enumerate(LORE_WEIGHTS)}
    return sorted(fragments, key=lambda item: (rank.get(item.weight, len(rank)), item.key))


def story_moment_due(bond: Bond, config: CompanionStoryConfig) -> bool:
    """Return whether a run starting now may offer a story moment."""
    every = config.story_moment_every_runs
    if every <= 0:
        return False
    if bond.last_story_run is None:
        return bond.completed_runs >= 1
    return bond.completed_runs - bond.last_story_run >= every


def _told(told: Mapping[str, ToldRecord], key: str) -> ToldRecord:
    return told.get(key) or ToldRecord()


def next_untold(
    fragments: Sequence[StoryItem],
    told: Mapping[str, ToldRecord],
    *,
    limit: int = 1,
) -> list[StoryItem]:
    """Return the next fragments of the arc this account has not heard yet.

    This is only a suggestion; the librarian decides whether to share. When
    every fragment has been told, the least-told (then the longest-ago) ones
    come round again, so the story never simply stops.
    """
    available = arc_order(fragments)
    untold = [item for item in available if _told(told, item.key).told_count == 0]
    if len(untold) >= limit:
        return untold[:limit]
    floor = datetime.min.replace(tzinfo=None)
    retold = sorted(
        (item for item in available if _told(told, item.key).told_count > 0),
        key=lambda item: (
            _told(told, item.key).told_count,
            (_told(told, item.key).last_told_at or floor).replace(tzinfo=None),
        ),
    )
    return [*untold, *retold][:limit]


def rank_topical(
    fragments: Sequence[StoryItem],
    similarity: Mapping[str, float] | None,
    told: Mapping[str, ToldRecord],
    *,
    limit: int,
    config: CompanionStoryConfig,
) -> list[RecalledFragment]:
    """Rank fragments by meaning (any weight); nothing without a semantic score.

    Only the raw similarity must clear ``config.topical_min_similarity``; the
    untold bonus and telling penalty then order the survivors.
    """
    if not similarity:
        return []
    settings = config
    ranked: list[RecalledFragment] = []
    for fragment in fragments:
        value = similarity.get(fragment.key)
        if value is None or value < settings.topical_min_similarity:
            continue
        count = _told(told, fragment.key).told_count
        score = value + (settings.untold_bonus if count == 0 else 0.0)
        score -= settings.told_penalty * min(count, settings.told_penalty_cap)
        ranked.append(RecalledFragment(fragment=fragment, score=round(score, 4)))
    ranked.sort(key=lambda item: (-item.score, item.fragment.key))
    return ranked[:limit]


def rank_self_query(
    fragments: Sequence[StoryItem],
    told: Mapping[str, ToldRecord],
    relevance: Mapping[str, float],
    *,
    limit: int,
    config: CompanionStoryConfig,
) -> list[RecalledFragment]:
    """Return the next untold fragments, the most relevant of a small window first."""
    window_size = config.self_query_window
    window = next_untold(fragments, told, limit=max(limit, window_size))
    order = {item.key: index for index, item in enumerate(window)}
    chosen = sorted(
        window,
        key=lambda item: (-round(relevance.get(item.key, 0.0), 4), order[item.key]),
    )[:limit]
    return [
        RecalledFragment(fragment=item, score=round(relevance.get(item.key, 0.0), 4))
        for item in chosen
    ]


__all__ = [
    "RecalledFragment",
    "arc_order",
    "cosine",
    "is_self_query",
    "is_semantic_embedder",
    "lexical_overlap",
    "next_untold",
    "rank_self_query",
    "rank_topical",
    "story_moment_due",
    "tokens",
]
