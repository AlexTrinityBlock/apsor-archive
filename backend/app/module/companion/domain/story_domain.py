"""Pure rules for companion stories: persona, lore fragments, weights, and recall.

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
from typing import Literal, cast

# How much a memory means to the librarian: everyday things, the past, and
# matters of the heart. A weight is metadata she can see, never a lock: every
# memory is hers to share or keep, whenever she judges the moment right.
LoreWeight = Literal["everyday", "past", "heart"]
StoryLocale = Literal["en", "zh-TW", "zh-CN"]

STORY_LOCALES: tuple[str, ...] = ("en", "zh-TW", "zh-CN")
DEFAULT_LOCALE = "en"

LORE_WEIGHTS: tuple[str, ...] = ("everyday", "past", "heart")
# Seed files written before weights used tiers; map them on read.
LEGACY_TIER_WEIGHTS: dict[str, str] = {
    "first": "everyday",
    "familiar": "past",
    "rare": "heart",
}
# Structural limits (schema sizes), not tunables.
PERSONA_MAX_CHARS = 4000
FRAGMENT_MAX_CHARS = 2000
FRAGMENT_KEY_MAX_CHARS = 64
MAX_FRAGMENTS_PER_COMPANION = 200
MAX_THEMES_PER_FRAGMENT = 12
THEME_MAX_CHARS = 40

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class CompanionStoryConfig:
    """Every tunable of companion stories: cadence, thresholds, words, guidance.

    Nothing here has a default: the shipped values live in the seed files
    (``lore/seed/config.json`` and ``lore/seed/templates``), root edits the live
    copy in the database, and services receive it through a config provider.

    - ``max_recalled_fragments``: fragments offered beside one search.
    - ``topical_min_similarity``: cosine bar for topical recall (semantic only;
      there is no keyword gate, so no topic is needed to "unlock" lore).
    - ``untold_bonus`` / ``told_penalty`` / ``told_penalty_cap``: prefer untold
      fragments; each earlier telling lowers a fragment a little.
    - ``story_moment_every_runs``: completed runs between story moments (0 off).
    - ``self_query_window``: how many upcoming untold fragments a self query ranks.
    - ``self_query_phrases`` / ``self_canon_terms``: explicit requests for the
      librarian's own story; canon terms count only as "your ..." / "你的...".
    - ``persona_rules`` / ``lore_guidance`` / ``story_moment_guidance``: text the
      model reads with the persona and with surfaced memories.
    """

    max_recalled_fragments: int
    topical_min_similarity: float
    untold_bonus: float
    told_penalty: float
    told_penalty_cap: int
    story_moment_every_runs: int
    self_query_window: int
    self_query_phrases: tuple[str, ...]
    self_canon_terms: tuple[str, ...]
    persona_rules: str
    lore_guidance: str
    story_moment_guidance: str


# Prompt-template keys the config provider serves (seeded, root-editable).
TEMPLATE_PERSONA_RULES = "persona_rules"
TEMPLATE_EQUAL_ADDRESS_RULE = "equal_address_rule"
TEMPLATE_LORE_GUIDANCE = "lore_guidance"
TEMPLATE_STORY_MOMENT_GUIDANCE = "story_moment_guidance"
TEMPLATE_MEMORY_AGENCY = "memory_agency"
TEMPLATE_CUSTOM_PERSONA_DEFAULT = "custom_persona_default"
TEMPLATE_LIFE_STORY_SYSTEM = "life_story_system"
TEMPLATE_LIFE_STORY_USER = "life_story_user"
TEMPLATE_KEYS: tuple[str, ...] = (
    TEMPLATE_PERSONA_RULES,
    TEMPLATE_EQUAL_ADDRESS_RULE,
    TEMPLATE_MEMORY_AGENCY,
    TEMPLATE_LORE_GUIDANCE,
    TEMPLATE_STORY_MOMENT_GUIDANCE,
    TEMPLATE_CUSTOM_PERSONA_DEFAULT,
    TEMPLATE_LIFE_STORY_SYSTEM,
    TEMPLATE_LIFE_STORY_USER,
)
# Placeholders each template must keep (the code fills them in).
TEMPLATE_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    TEMPLATE_PERSONA_RULES: (),
    TEMPLATE_EQUAL_ADDRESS_RULE: (),
    TEMPLATE_MEMORY_AGENCY: (),
    TEMPLATE_LORE_GUIDANCE: (),
    TEMPLATE_STORY_MOMENT_GUIDANCE: (),
    TEMPLATE_CUSTOM_PERSONA_DEFAULT: ("name",),
    TEMPLATE_LIFE_STORY_SYSTEM: ("companion_name", "persona", "language"),
    TEMPLATE_LIFE_STORY_USER: ("canon", "memories", "companion_name", "language", "max_chars"),
}


@dataclass(frozen=True)
class LifeStoryConfig:
    """Schedule and budgets of generated life stories (values come from the seed)."""

    enabled: bool
    every_conversations: int
    weight: LoreWeight
    max_per_30d: int
    memory_limit: int
    memory_chars: int
    canon_chars: int
    max_output_tokens: int
    max_chars: int
    require_review: bool
    poll_seconds: int
    max_attempts: int


@dataclass(frozen=True)
class CompanionRuntimeConfig(CompanionStoryConfig):
    """The live companion configuration for one account (or the global one).

    A :class:`CompanionStoryConfig` (so recall and pacing accept it unchanged)
    plus the per-run contribution cap, address rules, life-story schedule,
    prompt templates keyed by ``TEMPLATE_*``, and a version for cache keys.
    """

    max_contributions_per_run: int
    banned_address_terms: tuple[str, ...]
    life_story: LifeStoryConfig
    templates: tuple[tuple[str, str], ...] = ()
    version: int = 0

    def template(self, key: str, default: str = "") -> str:
        """Return the template body for ``key`` (or ``default`` when absent)."""
        for name, body in self.templates:
            if name == key:
                return body
        return default


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
    weight: LoreWeight
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
    """How long one account and one companion have known each other.

    Nothing here gates a memory. The librarian reads these facts and decides
    for herself what to share, and when.
    """

    completed_runs: int = 0
    conversations: int = 0
    # When they first spoke; ``None`` before the first completed run.
    first_met_at: datetime | None = None
    # ``completed_runs`` when the last story moment was offered; ``None`` before
    # the first one.
    last_story_run: int | None = None


@dataclass(frozen=True)
class Relationship:
    """Plain facts about the relationship the librarian may weigh."""

    first_met_at: datetime | None
    days_known: int
    conversations: int
    completed_runs: int


def relationship(bond: Bond, now: datetime) -> Relationship:
    """Return the relationship facts for ``bond`` as of ``now``."""
    days = 0
    if bond.first_met_at is not None:
        days = max(0, (now - bond.first_met_at).days)
    return Relationship(
        first_met_at=bond.first_met_at,
        days_known=days,
        conversations=bond.conversations,
        completed_runs=bond.completed_runs,
    )


def normalize_weight(value: object) -> LoreWeight:
    """Map a weight (or a legacy tier) to a weight; unknown values are everyday."""
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in LORE_WEIGHTS:
            return cast(LoreWeight, cleaned)
        mapped = LEGACY_TIER_WEIGHTS.get(cleaned)
        if mapped is not None:
            return cast(LoreWeight, mapped)
    return "everyday"


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


def render_template(template: str, values: dict[str, str]) -> str:
    """Fill ``{placeholder}`` slots; any other braces are left untouched."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered.strip()


def missing_placeholders(template_key: str, body: str) -> tuple[str, ...]:
    """Return the required placeholders ``body`` lost (empty when valid)."""
    required = TEMPLATE_PLACEHOLDERS.get(template_key, ())
    return tuple(name for name in required if "{" + name + "}" not in body)


def custom_persona(config: "CompanionRuntimeConfig", name: str) -> str:
    """Return the persona a custom companion has before its owner writes one."""
    return render_template(config.template(TEMPLATE_CUSTOM_PERSONA_DEFAULT), {"name": name})


def render_persona_section(persona: str, config: CompanionStoryConfig) -> str:
    """Return the persona followed by the rules that outrank it.

    The persona rules, the memory-agency note (her memories are hers to share
    or keep), and the equal-address rule all come from the config
    (root-editable templates seeded from ``lore/seed/templates``).
    """
    rules = config.persona_rules
    agency = ""
    equal_rule = ""
    if isinstance(config, CompanionRuntimeConfig):
        rules = config.template(TEMPLATE_PERSONA_RULES, rules) or rules
        agency = config.template(TEMPLATE_MEMORY_AGENCY, "")
        equal_rule = config.template(TEMPLATE_EQUAL_ADDRESS_RULE, "")
    parts = [persona.strip(), rules.strip(), agency.strip(), equal_rule.strip()]
    return "\n\n".join(part for part in parts if part)


@dataclass(frozen=True)
class ToldRecord:
    """How often one fragment has been told to this account, and when."""

    told_count: int = 0
    last_told_at: datetime | None = None


__all__ = [
    "DEFAULT_LOCALE",
    "FRAGMENT_KEY_MAX_CHARS",
    "FRAGMENT_MAX_CHARS",
    "LEGACY_TIER_WEIGHTS",
    "LORE_WEIGHTS",
    "MAX_FRAGMENTS_PER_COMPANION",
    "MAX_THEMES_PER_FRAGMENT",
    "PERSONA_MAX_CHARS",
    "STORY_ITEM_ORIGINS",
    "STORY_LOCALES",
    "TEMPLATE_CUSTOM_PERSONA_DEFAULT",
    "TEMPLATE_EQUAL_ADDRESS_RULE",
    "TEMPLATE_KEYS",
    "TEMPLATE_LIFE_STORY_SYSTEM",
    "TEMPLATE_LIFE_STORY_USER",
    "TEMPLATE_LORE_GUIDANCE",
    "TEMPLATE_MEMORY_AGENCY",
    "TEMPLATE_PERSONA_RULES",
    "TEMPLATE_PLACEHOLDERS",
    "TEMPLATE_STORY_MOMENT_GUIDANCE",
    "THEME_MAX_CHARS",
    "Bond",
    "CanonEntry",
    "CompanionRuntimeConfig",
    "CompanionStoryConfig",
    "LifeStoryConfig",
    "LoreFragment",
    "LoreWeight",
    "PresetStory",
    "Relationship",
    "StoryItem",
    "StoryItemOrigin",
    "StoryLocale",
    "ToldRecord",
    "WorldDoc",
    "WorldDocKind",
    "custom_persona",
    "is_fragment_key",
    "missing_placeholders",
    "normalize_locale",
    "normalize_themes",
    "normalize_weight",
    "relationship",
    "render_persona_section",
    "render_template",
]
