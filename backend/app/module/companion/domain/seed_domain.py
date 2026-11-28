"""Names shared by the companion seed bundle, the seeder, and the providers.

These are column-layout facts (which ``companion_config`` columns hold which
tunable), not tunable values: the values live in ``lore/seed/config.json`` and,
once seeded, in the database.
"""

from typing import Any, cast

from app.module.companion.domain.story_domain import (
    TEMPLATE_LORE_GUIDANCE,
    TEMPLATE_PERSONA_RULES,
    TEMPLATE_STORY_MOMENT_GUIDANCE,
    CompanionRuntimeConfig,
    LifeStoryConfig,
    LoreWeight,
)

SEED_BUNDLE = "companion"

TUNABLE_FIELDS: tuple[str, ...] = (
    "max_recalled_fragments",
    "topical_min_similarity",
    "untold_bonus",
    "told_penalty",
    "told_penalty_cap",
    "story_moment_every_runs",
    "self_query_window",
    "max_contributions_per_run",
)
LIFE_STORY_FIELDS: tuple[str, ...] = (
    "enabled",
    "every_conversations",
    "weight",
    "max_per_30d",
    "memory_limit",
    "memory_chars",
    "canon_chars",
    "max_output_tokens",
    "max_chars",
    "require_review",
    "poll_seconds",
    "max_attempts",
)
WORD_LIST_FIELDS: tuple[str, ...] = (
    "self_query_phrases",
    "self_canon_terms",
    "banned_address_terms",
)
# Every column of the config singleton that the seed and root edit.
CONFIG_COLUMNS: tuple[str, ...] = (
    *TUNABLE_FIELDS,
    *(f"life_story_{name}" for name in LIFE_STORY_FIELDS),
    *WORD_LIST_FIELDS,
)
# Per-account override columns (``companion_user_config``); NULL inherits.
USER_CONFIG_COLUMNS: tuple[str, ...] = (
    "max_recalled_fragments",
    "topical_min_similarity",
    "untold_bonus",
    "told_penalty",
    "told_penalty_cap",
    "story_moment_every_runs",
    "self_query_window",
    "max_contributions_per_run",
    "life_story_enabled",
    "life_story_every_conversations",
    "life_story_weight",
    "life_story_max_per_30d",
    "life_story_require_review",
)


def build_runtime_config(
    values: dict[str, Any],
    templates: dict[str, str],
    *,
    version: int = 0,
) -> CompanionRuntimeConfig:
    """Assemble a :class:`CompanionRuntimeConfig` from config columns and templates.

    ``values`` uses the ``companion_config`` column names; ``templates`` maps a
    template key to its body (English or the requested locale).
    """
    life = LifeStoryConfig(
        enabled=bool(values["life_story_enabled"]),
        every_conversations=int(values["life_story_every_conversations"]),
        weight=cast(LoreWeight, values["life_story_weight"]),
        max_per_30d=int(values["life_story_max_per_30d"]),
        memory_limit=int(values["life_story_memory_limit"]),
        memory_chars=int(values["life_story_memory_chars"]),
        canon_chars=int(values["life_story_canon_chars"]),
        max_output_tokens=int(values["life_story_max_output_tokens"]),
        max_chars=int(values["life_story_max_chars"]),
        require_review=bool(values["life_story_require_review"]),
        poll_seconds=int(values["life_story_poll_seconds"]),
        max_attempts=int(values["life_story_max_attempts"]),
    )
    return CompanionRuntimeConfig(
        max_recalled_fragments=int(values["max_recalled_fragments"]),
        topical_min_similarity=float(values["topical_min_similarity"]),
        untold_bonus=float(values["untold_bonus"]),
        told_penalty=float(values["told_penalty"]),
        told_penalty_cap=int(values["told_penalty_cap"]),
        story_moment_every_runs=int(values["story_moment_every_runs"]),
        self_query_window=int(values["self_query_window"]),
        self_query_phrases=tuple(str(item) for item in values["self_query_phrases"]),
        self_canon_terms=tuple(str(item) for item in values["self_canon_terms"]),
        persona_rules=templates.get(TEMPLATE_PERSONA_RULES, ""),
        lore_guidance=templates.get(TEMPLATE_LORE_GUIDANCE, ""),
        story_moment_guidance=templates.get(TEMPLATE_STORY_MOMENT_GUIDANCE, ""),
        max_contributions_per_run=int(values["max_contributions_per_run"]),
        banned_address_terms=tuple(str(item) for item in values["banned_address_terms"]),
        life_story=life,
        templates=tuple(sorted(templates.items())),
        version=version,
    )


__all__ = [
    "CONFIG_COLUMNS",
    "LIFE_STORY_FIELDS",
    "SEED_BUNDLE",
    "TUNABLE_FIELDS",
    "USER_CONFIG_COLUMNS",
    "WORD_LIST_FIELDS",
    "build_runtime_config",
]
