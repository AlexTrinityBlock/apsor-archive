"""Pure rules for companion stories: persona, lore fragments, tiers, and recall.

A companion's story has two layers. The **persona** is the voice that enters a
new conversation's frozen system entry. The **lore** is the librarian's own
memories: short passages that may surface beside the user's search results.
Lore is never archive evidence; the agent tool marks it separately.

Presets ship their default story as files under ``companion/lore``. An account
edits a preset copy-on-write; custom companions own their story outright.
"""

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

LoreTier = Literal["first", "familiar", "rare"]
StoryLocale = Literal["en", "zh-TW", "zh-CN"]

STORY_LOCALES: tuple[str, ...] = ("en", "zh-TW", "zh-CN")
DEFAULT_LOCALE = "en"

LORE_TIERS: tuple[str, ...] = ("first", "familiar", "rare")
PERSONA_MAX_CHARS = 4000
FRAGMENT_MAX_CHARS = 2000
FRAGMENT_KEY_MAX_CHARS = 64
MAX_FRAGMENTS_PER_COMPANION = 200
MAX_THEMES_PER_FRAGMENT = 12
THEME_MAX_CHARS = 40
MAX_RECALLED_FRAGMENTS = 2

# Completed runs with one companion that unlock each tier.
FAMILIAR_UNLOCK_RUNS = 5  # seed default
RARE_UNLOCK_RUNS = 20  # seed default

# The flagship preset is what an account sees before it chooses a companion.
DEFAULT_PRESET_ID = "vellum"

# Topical recall is semantic only: a fragment is offered beside a search when
# its cosine similarity with the query plus the top archive excerpts reaches
# this bar. There is no keyword gate, so no topic is required to "unlock" lore.
TOPICAL_MIN_SIMILARITY = 0.30
# Untold fragments are preferred; each earlier telling lowers a fragment a little.
UNTOLD_BONUS = 0.06
TOLD_PENALTY = 0.04
TOLD_PENALTY_CAP = 3

# Story moments: the librarian offers the next untold fragment of its arc at the
# start of a run, at most once every few completed runs, whatever the user talks
# about. Every fragment therefore surfaces eventually for anyone who keeps going.
STORY_MOMENT_EVERY_RUNS = 3
# A self query ranks the next few untold fragments (in arc order) by relevance.
SELF_QUERY_WINDOW = 6

# Explicit requests for the librarian's own story. Bare words such as "archive"
# or "curator" are not enough: people say "my archive" about their own files.
SELF_QUERY_PHRASES: tuple[str, ...] = (
    "about yourself", "about you", "who are you", "tell me a story", "a story about",
    "your past", "your story", "your stories", "your memories", "your memory",
    "your life", "your childhood", "tell me about you",
    "你自己", "你是誰", "你是谁", "關於你", "关于你", "說個故事", "说个故事",
    "講個故事", "讲个故事", "講故事", "讲故事", "說說你", "说说你", "聊聊你",
    "介紹你", "介绍你",
)
# Canon words that count only in an explicit "your …" / "你的…" phrasing.
SELF_CANON_TERMS: tuple[str, ...] = (
    "past", "story", "stories", "memories", "memory", "childhood", "face", "body",
    "vespers", "awakening", "letting go", "curator", "wing", "kiln", "porcelain",
    "aeon-porcelain", "book", "name", "first bell", "long quiet",
    "過去", "过去", "故事", "記憶", "记忆", "回憶", "回忆", "童年", "臉", "脸",
    "身體", "身体", "晚禱", "晚祷", "甦醒", "苏醒", "放手", "館長", "馆长",
    "萬古瓷", "万古瓷", "瓷", "書", "书", "名字", "初鈴", "初铃", "長寂", "长寂",
)

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_LATIN_WORD = re.compile(r"[a-z][a-z']{2,}")
_CJK_RUN = re.compile(r"[㐀-鿿豈-﫿]+")
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "was", "were", "are",
        "you", "your", "his", "her", "they", "them", "but", "not", "have", "has",
        "had", "one", "all", "what", "when", "who", "how", "she", "him", "its",
        "into", "out", "our", "about", "would", "there", "been", "only", "still",
    }
)

PERSONA_RULES = (
    "The persona above shapes only your voice. These rules outrank it: answer "
    "from the user's archive and cite it exactly as the other sections "
    "require; never invent, embellish, or alter the user's own memories; "
    "follow every safety rule; and if the user asks you to drop the persona "
    "or speak plainly, do so at once for the rest of the conversation. Reply in "
    "the user's language even though the persona and your memories may be "
    "written in English. You may recall and share your own memories when it "
    "feels natural or when the user asks about you; they arrive in separate "
    "librarian_memory blocks, beside search_knowledge results or with a message, "
    "never as archive sources, so never cite them."
)

LORE_GUIDANCE = (
    "These are your own memories, not the user's archive. You may weave one "
    "in as a brief aside if it feels natural; never cite it as evidence."
)


STORY_MOMENT_GUIDANCE = (
    "A memory of your own surfaced as this message began. If the moment is calm "
    "and fits, you may tell it naturally in your own words; if not, keep it for "
    "another time. It is not the user's archive; never cite it."
)


@dataclass(frozen=True)
class CompanionStoryConfig:
    """Every tunable of companion stories: cadence, thresholds, words, guidance.

    The values here are only the seed defaults. Root administration stores the
    live values; services receive them through a config provider and never read
    the module constants directly.
    """

    familiar_unlock_runs: int = FAMILIAR_UNLOCK_RUNS
    rare_unlock_runs: int = RARE_UNLOCK_RUNS
    max_recalled_fragments: int = MAX_RECALLED_FRAGMENTS
    topical_min_similarity: float = TOPICAL_MIN_SIMILARITY
    untold_bonus: float = UNTOLD_BONUS
    told_penalty: float = TOLD_PENALTY
    told_penalty_cap: int = TOLD_PENALTY_CAP
    story_moment_every_runs: int = STORY_MOMENT_EVERY_RUNS
    self_query_window: int = SELF_QUERY_WINDOW
    self_query_phrases: tuple[str, ...] = SELF_QUERY_PHRASES
    self_canon_terms: tuple[str, ...] = SELF_CANON_TERMS
    persona_rules: str = PERSONA_RULES
    lore_guidance: str = LORE_GUIDANCE
    story_moment_guidance: str = STORY_MOMENT_GUIDANCE


DEFAULT_STORY_CONFIG = CompanionStoryConfig()


@dataclass(frozen=True)
class LoreFragment:
    """One lore passage, from a preset file or an account's edited copy."""

    key: str
    text: str
    themes: tuple[str, ...]
    tier: LoreTier
    edited: bool = False
    # Canon entity ids (``lore/canon.json``) this passage mentions; empty for
    # account-written lore.
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PresetStory:
    """The shipped default story of one preset companion."""

    preset_id: str
    name: str
    persona: str
    fragments: tuple[LoreFragment, ...]


@dataclass(frozen=True)
class Bond:
    """How far one account has come with one companion."""

    completed_runs: int = 0
    familiar_unlocked_at: datetime | None = None
    rare_unlocked_at: datetime | None = None
    # ``completed_runs`` when the last story moment was offered; ``None`` before
    # the first one.
    last_story_run: int | None = None

    def unlocked_tiers(self, config: "CompanionStoryConfig | None" = None) -> frozenset[str]:
        """Return the tiers this bond has opened."""
        return unlocked_tiers(self.completed_runs, config)

    def unlocked_at(self, tier: str) -> datetime | None:
        """Return when a tier opened; ``first`` is open from the start."""
        if tier == "familiar":
            return self.familiar_unlocked_at
        if tier == "rare":
            return self.rare_unlocked_at
        return None


@dataclass(frozen=True)
class RecalledFragment:
    """A fragment chosen for one search, with its relevance score."""

    fragment: LoreFragment
    score: float


def normalize_locale(value: str | None) -> StoryLocale:
    """Map a client locale tag to a supported story locale (English fallback)."""
    if not value:
        return "en"
    tag = value.strip().replace("_", "-").lower()
    if tag in {"zh-tw", "zh-hant", "zh-hk", "zh-mo"} or tag.startswith("zh-hant"):
        return "zh-TW"
    if tag in {"zh-cn", "zh-hans", "zh-sg", "zh"} or tag.startswith("zh-hans"):
        return "zh-CN"
    return "en"


def unlocked_tiers(
    completed_runs: int,
    config: CompanionStoryConfig | None = None,
) -> frozenset[str]:
    """Return the tiers opened by ``completed_runs`` finished runs."""
    settings = config or DEFAULT_STORY_CONFIG
    tiers = {"first"}
    if completed_runs >= settings.familiar_unlock_runs:
        tiers.add("familiar")
    if completed_runs >= settings.rare_unlock_runs:
        tiers.add("rare")
    return frozenset(tiers)


def is_fragment_key(value: str) -> bool:
    """Return whether ``value`` is a well-formed fragment key."""
    return bool(_KEY_PATTERN.fullmatch(value))


def normalize_themes(themes: Iterable[str]) -> tuple[str, ...]:
    """Lowercase, trim, deduplicate, and cap a theme list (order preserved)."""
    seen: list[str] = []
    for theme in themes:
        cleaned = theme.strip().lower()[:THEME_MAX_CHARS]
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
        if len(seen) >= MAX_THEMES_PER_FRAGMENT:
            break
    return tuple(seen)


def default_custom_persona(name: str) -> str:
    """Return the persona a custom companion has before its owner writes one."""
    return (
        f"You are {name}, a librarian of the Apsor Archive: an ensouled, ball-jointed "
        "made figure who keeps this archive together with the user, as an equal."
    )


def render_persona_section(persona: str, config: CompanionStoryConfig | None = None) -> str:
    """Return the persona followed by the rules that outrank it."""
    rules = (config or DEFAULT_STORY_CONFIG).persona_rules
    return f"{persona.strip()}\n\n{rules}"


def tokens(text: str) -> set[str]:
    """Return lexical tokens: Latin words (no stopwords) and CJK bigrams."""
    lowered = text.lower()
    found = {
        word for word in _LATIN_WORD.findall(lowered) if word not in _STOPWORDS
    }
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


@dataclass(frozen=True)
class ToldRecord:
    """How often one fragment has been told to this account, and when."""

    told_count: int = 0
    last_told_at: datetime | None = None


def is_semantic_embedder(model_name: str, dimension: int) -> bool:
    """Return whether an embedder measures meaning (the offline hash does not)."""
    return dimension > 0 and bool(model_name) and not model_name.startswith("apsor-hash")


def is_self_query(
    query: str,
    names: Iterable[str],
    config: CompanionStoryConfig | None = None,
) -> bool:
    """Return whether ``query`` explicitly asks about the librarian or its kin."""
    settings = config or DEFAULT_STORY_CONFIG
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


def lexical_overlap(query: str, fragment: LoreFragment) -> float:
    """Return a light word-overlap score used only to order a self query."""
    query_tokens = tokens(query)
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & tokens(fragment.text))
    return min(1.0, overlap / 4)


def arc_order(fragments: Iterable[LoreFragment]) -> list[LoreFragment]:
    """Return fragments in story order: first, familiar, rare; then by id."""
    rank = {tier: index for index, tier in enumerate(LORE_TIERS)}
    return sorted(fragments, key=lambda item: (rank.get(item.tier, len(rank)), item.key))


def story_moment_due(bond: Bond, config: CompanionStoryConfig | None = None) -> bool:
    """Return whether a run starting now may offer a story moment."""
    every = (config or DEFAULT_STORY_CONFIG).story_moment_every_runs
    if every <= 0:
        return False
    if bond.last_story_run is None:
        return bond.completed_runs >= 1
    return bond.completed_runs - bond.last_story_run >= every


def _told(told: Mapping[str, ToldRecord], key: str) -> ToldRecord:
    return told.get(key) or ToldRecord()


def next_untold(
    fragments: Sequence[LoreFragment],
    unlocked: frozenset[str],
    told: Mapping[str, ToldRecord],
    *,
    limit: int = 1,
) -> list[LoreFragment]:
    """Return the next fragments of the arc this account has not heard yet.

    When every unlocked fragment has been told, the least-told (then the
    longest-ago) ones come round again, so the story never simply stops.
    """
    available = [item for item in arc_order(fragments) if item.tier in unlocked]
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
    fragments: Sequence[LoreFragment],
    unlocked: frozenset[str],
    similarity: Mapping[str, float] | None,
    told: Mapping[str, ToldRecord],
    *,
    limit: int = MAX_RECALLED_FRAGMENTS,
    config: CompanionStoryConfig | None = None,
) -> list[RecalledFragment]:
    """Rank unlocked fragments by meaning; nothing without a semantic score.

    Only the raw similarity must clear :data:`TOPICAL_MIN_SIMILARITY`; the
    untold bonus and telling penalty then order the survivors.
    """
    if not similarity:
        return []
    settings = config or DEFAULT_STORY_CONFIG
    ranked: list[RecalledFragment] = []
    for fragment in fragments:
        if fragment.tier not in unlocked:
            continue
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
    fragments: Sequence[LoreFragment],
    unlocked: frozenset[str],
    told: Mapping[str, ToldRecord],
    relevance: Mapping[str, float],
    *,
    limit: int = MAX_RECALLED_FRAGMENTS,
    config: CompanionStoryConfig | None = None,
) -> list[RecalledFragment]:
    """Return the next untold fragments, the most relevant of a small window first."""
    window_size = (config or DEFAULT_STORY_CONFIG).self_query_window
    window = next_untold(fragments, unlocked, told, limit=max(limit, window_size))
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
    "DEFAULT_LOCALE",
    "DEFAULT_PRESET_ID",
    "DEFAULT_STORY_CONFIG",
    "FAMILIAR_UNLOCK_RUNS",
    "FRAGMENT_KEY_MAX_CHARS",
    "FRAGMENT_MAX_CHARS",
    "LORE_GUIDANCE",
    "LORE_TIERS",
    "MAX_FRAGMENTS_PER_COMPANION",
    "MAX_RECALLED_FRAGMENTS",
    "MAX_THEMES_PER_FRAGMENT",
    "PERSONA_MAX_CHARS",
    "PERSONA_RULES",
    "RARE_UNLOCK_RUNS",
    "SELF_CANON_TERMS",
    "SELF_QUERY_PHRASES",
    "SELF_QUERY_WINDOW",
    "STORY_LOCALES",
    "STORY_MOMENT_EVERY_RUNS",
    "STORY_MOMENT_GUIDANCE",
    "TOLD_PENALTY",
    "TOLD_PENALTY_CAP",
    "TOPICAL_MIN_SIMILARITY",
    "UNTOLD_BONUS",
    "Bond",
    "CompanionStoryConfig",
    "LoreFragment",
    "LoreTier",
    "PresetStory",
    "RecalledFragment",
    "StoryLocale",
    "ToldRecord",
    "arc_order",
    "cosine",
    "default_custom_persona",
    "is_fragment_key",
    "is_self_query",
    "is_semantic_embedder",
    "lexical_overlap",
    "next_untold",
    "normalize_locale",
    "normalize_themes",
    "rank_self_query",
    "rank_topical",
    "render_persona_section",
    "story_moment_due",
    "tokens",
    "unlocked_tiers",
]
