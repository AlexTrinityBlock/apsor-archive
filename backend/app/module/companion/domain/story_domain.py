"""Pure rules for companion stories: persona, lore fragments, tiers, and recall.

A companion's story has two layers. The **persona** is the voice that enters a
new conversation's frozen system entry. The **lore** is the librarian's own
memories: short passages that may surface beside the Keeper's search results.
Lore is never archive evidence; the agent tool marks it separately.

Presets ship their default story as files under ``companion/lore``. An account
edits a preset copy-on-write; custom companions own their story outright.
"""

import math
import re
from collections.abc import Iterable, Sequence
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
FAMILIAR_UNLOCK_RUNS = 5
RARE_UNLOCK_RUNS = 20

# The flagship preset is what an account sees before it chooses a companion.
DEFAULT_PRESET_ID = "vellum"

# Minimum relevance before a fragment is offered at all. Frequency is otherwise
# left to the model, which decides whether to weave the offered memory in.
RECALL_MIN_SCORE = 0.12
# A question about the librarian itself (its past, the Archive, the other
# librarians) lowers the bar so its own story can answer it.
SELF_RECALL_MIN_SCORE = 0.04
SELF_QUERY_BONUS = 0.25

# Words that turn a search into a question about the librarian or the Archive
# canon. Preset and companion names are added at runtime.
SELF_QUERY_TERMS: tuple[str, ...] = (
    "librarian", "librarians", "apsor", "the archive", "yourself", "your past",
    "your story", "your memories", "who are you", "about you", "marionette",
    "head librarian",
    "圖書館員", "图书馆员", "你自己", "你的過去", "你的过去", "你的故事", "你的記憶",
    "你的记忆", "你是誰", "你是谁", "關於你", "关于你", "檔案館", "档案馆", "人偶",
    "館長", "馆长",
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
    "from the Keeper's archive and cite it exactly as the other sections "
    "require; never invent, embellish, or alter the Keeper's own memories; "
    "follow every safety rule; and if the Keeper asks you to drop the persona "
    "or speak plainly, do so at once for the rest of the conversation. Reply in "
    "the Keeper's language even though the persona and your memories may be "
    "written in English. You may recall and share your own memories when it "
    "feels natural or when the Keeper asks about you; they arrive from "
    "search_knowledge in a separate librarian_memory block, never as archive "
    "sources, so never cite them."
)

LORE_GUIDANCE = (
    "These are your own memories, not the Keeper's archive. You may weave one "
    "in as a brief aside if it feels natural; never cite it as evidence."
)


@dataclass(frozen=True)
class LoreFragment:
    """One lore passage, from a preset file or an account's edited copy."""

    key: str
    text: str
    themes: tuple[str, ...]
    tier: LoreTier
    edited: bool = False


@dataclass(frozen=True)
class PresetStory:
    """The shipped default story of one preset companion."""

    preset_id: str
    name: str
    persona: str
    fragments: tuple[LoreFragment, ...]


@dataclass(frozen=True)
class LoreVocabulary:
    """Multilingual keywords per theme, so a Chinese query can find English lore."""

    themes: dict[str, tuple[str, ...]]

    def themes_in(self, text: str) -> set[str]:
        """Return every theme whose keywords appear in ``text``."""
        lowered = text.lower()
        found: set[str] = set()
        for theme, keywords in self.themes.items():
            if any(keyword and keyword in lowered for keyword in keywords):
                found.add(theme)
        return found


@dataclass(frozen=True)
class Bond:
    """How far one account has come with one companion."""

    completed_runs: int = 0
    familiar_unlocked_at: datetime | None = None
    rare_unlocked_at: datetime | None = None

    def unlocked_tiers(self) -> frozenset[str]:
        """Return the tiers this bond has opened."""
        return unlocked_tiers(self.completed_runs)

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


def unlocked_tiers(completed_runs: int) -> frozenset[str]:
    """Return the tiers opened by ``completed_runs`` finished runs."""
    tiers = {"first"}
    if completed_runs >= FAMILIAR_UNLOCK_RUNS:
        tiers.add("familiar")
    if completed_runs >= RARE_UNLOCK_RUNS:
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
        f"You are {name}, a librarian of the Apsor Archive: an ensouled marionette "
        "who keeps the Keeper's memories with quiet care."
    )


def render_persona_section(persona: str) -> str:
    """Return the persona followed by the rules that outrank it."""
    return f"{persona.strip()}\n\n{PERSONA_RULES}"


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


def lexical_score(
    context: str,
    fragment: LoreFragment,
    vocabulary: LoreVocabulary,
) -> float:
    """Score theme overlap (through the vocabulary) plus direct word overlap."""
    context_themes = vocabulary.themes_in(context) | (tokens(context) & set(fragment.themes))
    theme_hits = len(context_themes & set(fragment.themes))
    theme_score = min(1.0, theme_hits / 2)
    context_tokens = tokens(context)
    fragment_tokens = tokens(fragment.text)
    if not context_tokens or not fragment_tokens:
        word_score = 0.0
    else:
        overlap = len(context_tokens & fragment_tokens)
        word_score = min(1.0, overlap / 4)
    return 0.7 * theme_score + 0.3 * word_score


def is_self_query(query: str, names: Iterable[str]) -> bool:
    """Return whether ``query`` asks about the librarian, its kin, or the Archive."""
    lowered = query.lower()
    if any(term in lowered for term in SELF_QUERY_TERMS):
        return True
    return any(name and name.lower() in lowered for name in names)


def select_fragments(
    *,
    fragments: Sequence[LoreFragment],
    unlocked: frozenset[str],
    lexical: dict[str, float],
    semantic: dict[str, float] | None,
    self_query: bool = False,
    limit: int = MAX_RECALLED_FRAGMENTS,
) -> list[RecalledFragment]:
    """Rank unlocked fragments and return at most ``limit`` relevant ones.

    ``lexical`` and ``semantic`` map fragment keys to scores in ``[0, 1]``.
    Without semantic scores the lexical score stands alone. A self query adds a
    flat bonus and lowers the threshold so the librarian can tell its own story.
    """
    threshold = SELF_RECALL_MIN_SCORE if self_query else RECALL_MIN_SCORE
    ranked: list[RecalledFragment] = []
    for fragment in fragments:
        if fragment.tier not in unlocked:
            continue
        lexical_value = lexical.get(fragment.key, 0.0)
        if semantic is None:
            score = lexical_value
        else:
            score = 0.55 * max(0.0, semantic.get(fragment.key, 0.0)) + 0.45 * lexical_value
        if self_query:
            score += SELF_QUERY_BONUS
        if score >= threshold:
            ranked.append(RecalledFragment(fragment=fragment, score=round(score, 4)))
    ranked.sort(key=lambda item: (-item.score, item.fragment.key))
    return ranked[:limit]


__all__ = [
    "DEFAULT_LOCALE",
    "DEFAULT_PRESET_ID",
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
    "RECALL_MIN_SCORE",
    "SELF_QUERY_BONUS",
    "SELF_QUERY_TERMS",
    "SELF_RECALL_MIN_SCORE",
    "STORY_LOCALES",
    "Bond",
    "LoreFragment",
    "LoreTier",
    "LoreVocabulary",
    "PresetStory",
    "RecalledFragment",
    "StoryLocale",
    "cosine",
    "default_custom_persona",
    "is_fragment_key",
    "is_self_query",
    "lexical_score",
    "normalize_locale",
    "normalize_themes",
    "render_persona_section",
    "select_fragments",
    "tokens",
    "unlocked_tiers",
]
