"""Pure rules for companion stories: persona, lore fragments, tiers, and recall.

A companion's story has two layers. The **persona** is the voice that enters a
new conversation's frozen system entry. The **lore** is the librarian's own
memories: short passages that may surface beside the user's search results.
Lore is never archive evidence; the agent tool marks it separately.

Presets ship their default story as files under ``companion/lore``. An account
edits a preset copy-on-write; custom companions own their story outright.
"""

import re
from collections.abc import Iterable
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
    "about yourself",
    "about you",
    "who are you",
    "tell me a story",
    "a story about",
    "your past",
    "your story",
    "your stories",
    "your memories",
    "your memory",
    "your life",
    "your childhood",
    "tell me about you",
    "你自己",
    "你是誰",
    "你是谁",
    "關於你",
    "关于你",
    "說個故事",
    "说个故事",
    "講個故事",
    "讲个故事",
    "講故事",
    "讲故事",
    "說說你",
    "说说你",
    "聊聊你",
    "介紹你",
    "介绍你",
)
# Canon words that count only in an explicit "your …" / "你的…" phrasing.
SELF_CANON_TERMS: tuple[str, ...] = (
    "past",
    "story",
    "stories",
    "memories",
    "memory",
    "childhood",
    "face",
    "body",
    "vespers",
    "awakening",
    "letting go",
    "curator",
    "wing",
    "kiln",
    "porcelain",
    "aeon-porcelain",
    "book",
    "name",
    "first bell",
    "long quiet",
    "過去",
    "过去",
    "故事",
    "記憶",
    "记忆",
    "回憶",
    "回忆",
    "童年",
    "臉",
    "脸",
    "身體",
    "身体",
    "晚禱",
    "晚祷",
    "甦醒",
    "苏醒",
    "放手",
    "館長",
    "馆长",
    "萬古瓷",
    "万古瓷",
    "瓷",
    "書",
    "书",
    "名字",
    "初鈴",
    "初铃",
    "長寂",
    "长寂",
)

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

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

# Address terms a generated or edited story must never use for the person.
BANNED_ADDRESS_TERMS: tuple[str, ...] = (
    "keeper",
    "master",
    "my lord",
    "my lady",
    "館主",
    "馆主",
    "主人",
    "主公",
)

# Prompt-template keys the config provider serves (seeded, root-editable).
TEMPLATE_PERSONA_RULES = "persona_rules"
TEMPLATE_EQUAL_ADDRESS_RULE = "equal_address_rule"
TEMPLATE_LORE_GUIDANCE = "lore_guidance"
TEMPLATE_STORY_MOMENT_GUIDANCE = "story_moment_guidance"
TEMPLATE_CUSTOM_PERSONA_DEFAULT = "custom_persona_default"
TEMPLATE_LIFE_STORY_SYSTEM = "life_story_system"
TEMPLATE_LIFE_STORY_USER = "life_story_user"
TEMPLATE_KEYS: tuple[str, ...] = (
    TEMPLATE_PERSONA_RULES,
    TEMPLATE_EQUAL_ADDRESS_RULE,
    TEMPLATE_LORE_GUIDANCE,
    TEMPLATE_STORY_MOMENT_GUIDANCE,
    TEMPLATE_CUSTOM_PERSONA_DEFAULT,
    TEMPLATE_LIFE_STORY_SYSTEM,
    TEMPLATE_LIFE_STORY_USER,
)


@dataclass(frozen=True)
class LifeStoryConfig:
    """Schedule and budgets of generated life stories (seed defaults)."""

    enabled: bool = True
    every_conversations: int = 5
    tier: LoreTier = "familiar"
    max_per_30d: int = 4
    memory_limit: int = 8
    memory_chars: int = 6000
    canon_chars: int = 4000
    max_output_tokens: int = 1500
    max_chars: int = 2400
    require_review: bool = False
    poll_seconds: int = 30
    max_attempts: int = 3


DEFAULT_LIFE_STORY_CONFIG = LifeStoryConfig()


@dataclass(frozen=True)
class CompanionRuntimeConfig(CompanionStoryConfig):
    """The live companion configuration for one account (or the global one).

    A :class:`CompanionStoryConfig` (so recall and pacing accept it unchanged)
    plus the per-run contribution cap, address rules, life-story schedule,
    prompt templates keyed by ``TEMPLATE_*``, and a version for cache keys.
    """

    max_contributions_per_run: int = 2
    banned_address_terms: tuple[str, ...] = BANNED_ADDRESS_TERMS
    life_story: LifeStoryConfig = DEFAULT_LIFE_STORY_CONFIG
    templates: tuple[tuple[str, str], ...] = ()
    version: int = 0

    def template(self, key: str, default: str = "") -> str:
        """Return the template body for ``key`` (or ``default`` when absent)."""
        for name, body in self.templates:
            if name == key:
                return body
        return default


DEFAULT_RUNTIME_CONFIG = CompanionRuntimeConfig(
    templates=(
        (TEMPLATE_PERSONA_RULES, PERSONA_RULES),
        (TEMPLATE_LORE_GUIDANCE, LORE_GUIDANCE),
        (TEMPLATE_STORY_MOMENT_GUIDANCE, STORY_MOMENT_GUIDANCE),
    ),
)


StoryItemOrigin = Literal["preset", "admin", "user", "generated"]
STORY_ITEM_ORIGINS: tuple[str, ...] = ("preset", "admin", "user", "generated")


@dataclass(frozen=True)
class StoryItem:
    """One lore passage, whatever layer it came from.

    ``origin`` names the layer: a shipped/root-edited preset item, root's
    per-account override, the account's own copy-on-write edit, or a generated
    life story. Recall and pacing treat every origin the same way.
    """

    key: str
    text: str
    themes: tuple[str, ...]
    tier: LoreTier
    edited: bool = False
    # Canon entity ids (``lore/canon.json``) this passage mentions; empty for
    # account-written lore.
    refs: tuple[str, ...] = ()
    origin: StoryItemOrigin = "preset"


# Backward-compatible name used across the slice and the tests.
LoreFragment = StoryItem


@dataclass(frozen=True)
class PresetStory:
    """The shipped default story of one preset companion."""

    preset_id: str
    name: str
    persona: str
    fragments: tuple[StoryItem, ...]


@dataclass(frozen=True)
class CanonEntry:
    """One canon entity in one locale."""

    entity_id: str
    name: str
    summary: str


WorldDocKind = Literal["bible", "glossary", "world", "terms", "character"]


@dataclass(frozen=True)
class WorldDoc:
    """One world document (bible, glossary, world, terms, character) in one locale."""

    doc_key: str
    locale: str
    kind: WorldDocKind
    title: str
    body_md: str
    version: int = 1


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


@dataclass(frozen=True)
class ToldRecord:
    """How often one fragment has been told to this account, and when."""

    told_count: int = 0
    last_told_at: datetime | None = None


__all__ = [
    "BANNED_ADDRESS_TERMS",
    "DEFAULT_LIFE_STORY_CONFIG",
    "DEFAULT_LOCALE",
    "DEFAULT_PRESET_ID",
    "DEFAULT_RUNTIME_CONFIG",
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
    "STORY_ITEM_ORIGINS",
    "STORY_LOCALES",
    "STORY_MOMENT_EVERY_RUNS",
    "STORY_MOMENT_GUIDANCE",
    "TEMPLATE_CUSTOM_PERSONA_DEFAULT",
    "TEMPLATE_EQUAL_ADDRESS_RULE",
    "TEMPLATE_KEYS",
    "TEMPLATE_LIFE_STORY_SYSTEM",
    "TEMPLATE_LIFE_STORY_USER",
    "TEMPLATE_LORE_GUIDANCE",
    "TEMPLATE_PERSONA_RULES",
    "TEMPLATE_STORY_MOMENT_GUIDANCE",
    "TOLD_PENALTY",
    "TOLD_PENALTY_CAP",
    "TOPICAL_MIN_SIMILARITY",
    "UNTOLD_BONUS",
    "Bond",
    "CanonEntry",
    "CompanionRuntimeConfig",
    "CompanionStoryConfig",
    "LifeStoryConfig",
    "LoreFragment",
    "LoreTier",
    "PresetStory",
    "StoryItem",
    "StoryItemOrigin",
    "StoryLocale",
    "ToldRecord",
    "WorldDoc",
    "WorldDocKind",
    "default_custom_persona",
    "is_fragment_key",
    "normalize_locale",
    "normalize_themes",
    "render_persona_section",
    "unlocked_tiers",
]
