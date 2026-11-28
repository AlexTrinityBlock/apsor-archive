"""Root's companion administration: global world content and per-account stories.

Runs on a store whose session carries the companion admin scope. Reading a
generated story's full text, and every per-account write, appends a row to
``companion_admin_access_log``. Global rows that are still only in the shipped
seed files are shown read-through (``seeded=False``) and materialized on first
edit, so the admin view works before the seeder has run.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from app.module.companion.domain.companion_policy_domain import (
    AccountCompanionPolicy,
    AdminLoreOverride,
    StoryLayers,
    allowed_refs,
    resolve_active_companion,
    resolve_persona,
    resolve_story_items,
)
from app.module.companion.domain.story_domain import (
    DEFAULT_PRESET_ID,
    DEFAULT_RUNTIME_CONFIG,
    TEMPLATE_CUSTOM_PERSONA_DEFAULT,
    TEMPLATE_KEYS,
    TEMPLATE_LIFE_STORY_USER,
    PresetStory,
    StoryItem,
    default_custom_persona,
    normalize_themes,
    unlocked_tiers,
)
from app.module.companion.exception.domain_error import (
    CompanionInvalidError,
    CompanionLoreNotFoundError,
    CompanionNotFoundError,
    CompanionRefNotFoundError,
)
from app.module.companion.model.companion_admin_model import (
    CompanionAccountPolicyModel,
    CompanionAdminLoreOverrideModel,
    CompanionAdminStoryOverrideModel,
    CompanionUserConfigModel,
)
from app.module.companion.model.companion_life_story_model import (
    CompanionGeneratedStoryModel,
    CompanionStoryJobModel,
)
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreToldModel,
)
from app.module.companion.model.companion_world_model import (
    CompanionCanonEntityModel,
    CompanionConfigModel,
    CompanionLoreItemModel,
    CompanionLoreItemTextModel,
    CompanionPresetModel,
    CompanionPresetTextModel,
    CompanionPromptTemplateModel,
    CompanionWorldDocModel,
    CompanionWorldDocRevisionModel,
)
from app.module.companion.protocol.companion_admin_protocol import (
    AccountRow,
    CompanionAdminStoreProtocol,
    CompanionSeederProtocol,
)
from app.module.companion.schema.companion_admin_schema import (
    CompanionAccessLogSchema,
    CompanionBondAdminSchema,
    CompanionBondAdminUpdateSchema,
    CompanionCanonEntitySchema,
    CompanionCanonEntityUpsertSchema,
    CompanionConfigAdminSchema,
    CompanionConfigAdminUpdateSchema,
    CompanionConfigKnobSchema,
    CompanionFragmentProgressUpdateSchema,
    CompanionGeneratedStorySchema,
    CompanionGeneratedStorySummarySchema,
    CompanionGeneratedStoryUpdateSchema,
    CompanionLoreItemAdminCreateSchema,
    CompanionLoreItemAdminSchema,
    CompanionLoreItemAdminUpdateSchema,
    CompanionLoreOverrideSchema,
    CompanionLoreOverrideUpsertSchema,
    CompanionPersonaOverrideSchema,
    CompanionPersonaOverrideUpdateSchema,
    CompanionPolicyAdminSchema,
    CompanionPolicyAdminUpdateSchema,
    CompanionPresetAdminSchema,
    CompanionPresetAdminUpdateSchema,
    CompanionPresetCatalogSchema,
    CompanionPresetOptionSchema,
    CompanionPresetTextAdminSchema,
    CompanionPresetTextAdminUpdateSchema,
    CompanionProgressResetSchema,
    CompanionSeedApplySchema,
    CompanionSeedStatusSchema,
    CompanionStoryGenerateSchema,
    CompanionStoryJobSchema,
    CompanionTemplateAdminSchema,
    CompanionTemplateAdminUpdateSchema,
    CompanionTemplatePreviewRequestSchema,
    CompanionTemplatePreviewSchema,
    CompanionUserAdminSchema,
    CompanionUserConfigAdminSchema,
    CompanionUserConfigAdminUpdateSchema,
    CompanionUserFragmentSchema,
    CompanionUserFragmentsSchema,
    CompanionUserSummarySchema,
    CompanionWorldDocRevisionSchema,
    CompanionWorldDocSchema,
    CompanionWorldDocSummarySchema,
    CompanionWorldDocUpdateSchema,
)
from app.module.companion.service.preset_lore_catalog import load_presets
from app.module.companion.service.story_config import StaticCompanionContentProvider

LOCALES: tuple[str, ...] = ("en", "zh-TW", "zh-CN")
WORLD_DOC_KEYS: tuple[str, ...] = ("bible", "glossary", "world", "terms")
REVISIONS_KEPT = 20
ACTIVITY_WEEKS = 8
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

REQUIRED_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    TEMPLATE_CUSTOM_PERSONA_DEFAULT: ("name",),
    TEMPLATE_LIFE_STORY_USER: (
        "companion_name",
        "persona",
        "canon",
        "memories",
        "language",
        "max_chars",
    ),
}

# A fictional sample: template previews never read a real archive.
SAMPLE_VALUES: dict[str, str] = {
    "name": "Ember",
    "companion_name": "Vellum",
    "persona": "Vellum keeps the East Wing at night and speaks softly, as an equal.",
    "canon": "The Curator's Rule: we never destroy, we only archive. The Letting Go.",
    "memories": (
        "- (memory) Sunday walk to the bakery on the corner; the baker saves the last rye loaf.\n"
        "- (memory) A balcony tomato plant that finally fruited in late August."
    ),
    "language": "English",
    "max_chars": "2400",
}


@dataclass(frozen=True)
class _Knob:
    key: str
    kind: str
    group: str
    minimum: float | None = None
    maximum: float | None = None
    per_user: bool = True


KNOBS: tuple[_Knob, ...] = (
    _Knob("familiar_unlock_runs", "int", "unlock", 0, 1000),
    _Knob("rare_unlock_runs", "int", "unlock", 0, 10000),
    _Knob("max_recalled_fragments", "int", "recall", 0, 5),
    _Knob("topical_min_similarity", "float", "recall", 0, 1),
    _Knob("untold_bonus", "float", "recall", 0, 1),
    _Knob("told_penalty", "float", "recall", 0, 1),
    _Knob("told_penalty_cap", "int", "recall", 0, 20),
    _Knob("story_moment_every_runs", "int", "pacing", 0, 100),
    _Knob("self_query_window", "int", "pacing", 1, 50),
    _Knob("max_contributions_per_run", "int", "pacing", 0, 5),
    _Knob("life_story_enabled", "bool", "life_story"),
    _Knob("life_story_every_conversations", "int", "life_story", 3, 1000),
    _Knob("life_story_tier", "tier", "life_story"),
    _Knob("life_story_max_per_30d", "int", "life_story", 0, 60),
    _Knob("life_story_require_review", "bool", "life_story"),
    _Knob("life_story_memory_limit", "int", "life_story", 1, 40, per_user=False),
    _Knob("life_story_memory_chars", "int", "life_story", 500, 20000, per_user=False),
    _Knob("life_story_canon_chars", "int", "life_story", 500, 20000, per_user=False),
    _Knob("life_story_max_output_tokens", "int", "life_story", 200, 8000, per_user=False),
    _Knob("life_story_max_chars", "int", "life_story", 400, 4000, per_user=False),
    _Knob("life_story_poll_seconds", "int", "life_story", 5, 3600, per_user=False),
    _Knob("life_story_max_attempts", "int", "life_story", 1, 10, per_user=False),
    _Knob("self_query_phrases", "list", "words", per_user=False),
    _Knob("self_canon_terms", "list", "words", per_user=False),
    _Knob("banned_address_terms", "list", "words", per_user=False),
)
_KNOB_BY_KEY = {knob.key: knob for knob in KNOBS}
_TIERS = ("first", "familiar", "rare")


def knob_default(key: str) -> Any:
    """Return the shipped default for one tunable."""
    if key.startswith("life_story_"):
        value = getattr(DEFAULT_RUNTIME_CONFIG.life_story, key.removeprefix("life_story_"))
    else:
        value = getattr(DEFAULT_RUNTIME_CONFIG, key)
    return list(value) if isinstance(value, tuple) else value


def coerce_knob(key: str, value: Any) -> Any:
    """Validate one tunable value against its kind and bounds."""
    knob = _KNOB_BY_KEY.get(key)
    if knob is None:
        raise CompanionInvalidError(f"Unknown setting {key!r}.")
    if knob.kind == "bool":
        if not isinstance(value, bool):
            raise CompanionInvalidError(f"{key} must be true or false.")
        return value
    if knob.kind == "tier":
        if value not in _TIERS:
            raise CompanionInvalidError(f"{key} must be first, familiar, or rare.")
        return value
    if knob.kind == "list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise CompanionInvalidError(f"{key} must be a list of words.")
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) > 200 or any(len(item) > 80 for item in cleaned):
            raise CompanionInvalidError(f"{key} has too many or too long entries.")
        return cleaned
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CompanionInvalidError(f"{key} must be a number.")
    number: float | int = int(value) if knob.kind == "int" else float(value)
    if knob.kind == "int" and value != int(value):
        raise CompanionInvalidError(f"{key} must be a whole number.")
    if (knob.minimum is not None and number < knob.minimum) or (
        knob.maximum is not None and number > knob.maximum
    ):
        raise CompanionInvalidError(f"{key} must be between {knob.minimum} and {knob.maximum}.")
    return number


def placeholders(body: str) -> list[str]:
    """Return the ``{placeholder}`` names used in a template body, in order."""
    seen: list[str] = []
    for name in _PLACEHOLDER.findall(body):
        if name not in seen:
            seen.append(name)
    return seen


def render_sample(body: str) -> str:
    """Render a template against the fictional sample, leaving unknown names."""
    return _PLACEHOLDER.sub(lambda match: SAMPLE_VALUES.get(match.group(1), match.group(0)), body)


@lru_cache(maxsize=4)
def _seed_presets(locale: str) -> dict[str, PresetStory]:
    return load_presets(locale)


def _seed_preset(preset_id: str, locale: str) -> PresetStory | None:
    return _seed_presets(locale).get(preset_id)


def _upstream(row: Any) -> bool:
    return bool(row.upstream_seed_hash and row.upstream_seed_hash != row.seed_hash)


def _ref_preset(companion_ref: str) -> str | None:
    return companion_ref.split(":", 1)[1] if companion_ref.startswith("preset:") else None


def _ref_custom(companion_ref: str) -> int | None:
    if not companion_ref.startswith("custom:"):
        return None
    tail = companion_ref.split(":", 1)[1]
    return int(tail) if tail.isdigit() else None


def _source_counts(source_refs: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in source_refs.items():
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, int):
            counts[key] = value
    return counts


class CompanionAdminService:
    """Root-only companion administration on an admin-scoped store."""

    def __init__(
        self,
        store: CompanionAdminStoreProtocol,
        *,
        actor_user_id: int,
        seeder: CompanionSeederProtocol | None = None,
        clock: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.actor_user_id = actor_user_id
        self.seeder = seeder
        self.clock = clock
        self._static = StaticCompanionContentProvider()

    # --- shared helpers -------------------------------------------------------

    async def _log(
        self,
        target_user_id: int,
        action: str,
        *,
        story_id: int | None = None,
        companion_ref: str | None = None,
    ) -> None:
        await self.store.log_access(
            actor_user_id=self.actor_user_id,
            target_user_id=target_user_id,
            action=action,
            story_id=story_id,
            companion_ref=companion_ref,
            at=self.clock(),
        )

    async def _account(self, user_id: int) -> AccountRow:
        account = await self.store.get_account(user_id)
        if account is None:
            raise CompanionNotFoundError(user_id)
        return account

    async def _preset_ids(self, *, enabled_only: bool = True) -> list[str]:
        rows = await self.store.list_presets()
        if rows:
            return [row.id for row in rows if row.enabled or not enabled_only]
        return await self._static.enabled_preset_ids()

    async def _global_default(self) -> str:
        rows = await self.store.list_presets()
        for row in rows:
            if row.is_global_default and row.enabled:
                return f"preset:{row.id}"
        return f"preset:{await self._static.global_default_preset_id()}"

    async def _custom_refs(self, user_id: int) -> list[str]:
        return [f"custom:{row.id}" for row in await self.store.list_custom_companions(user_id)]

    async def _ref_name(self, companion_ref: str, user_id: int, locale: str = "en") -> str:
        preset_id = _ref_preset(companion_ref)
        if preset_id is not None:
            text = await self.store.get_preset_text(preset_id, locale)
            if text is None and locale != "en":
                text = await self.store.get_preset_text(preset_id, "en")
            if text is not None:
                return text.name
            seed = _seed_preset(preset_id, locale) or _seed_preset(preset_id, "en")
            return seed.name if seed else preset_id
        custom_id = _ref_custom(companion_ref)
        for row in await self.store.list_custom_companions(user_id):
            if row.id == custom_id:
                return row.name
        return companion_ref

    async def _materialize_preset(self, preset_id: str) -> CompanionPresetModel:
        row = await self.store.get_preset(preset_id)
        if row is not None:
            return row
        seed_ids = list(_seed_presets("en"))
        if preset_id not in seed_ids:
            raise CompanionRefNotFoundError(f"preset:{preset_id}")
        row = CompanionPresetModel(
            id=preset_id,
            position=seed_ids.index(preset_id),
            enabled=True,
            is_global_default=preset_id == DEFAULT_PRESET_ID
            and not any(p.is_global_default for p in await self.store.list_presets()),
            updated_by_user_id=self.actor_user_id,
        )
        await self.store.add(row)
        return row

    async def _effective_config(self) -> dict[str, Any]:
        row = await self.store.get_config()
        values: dict[str, Any] = {}
        for knob in KNOBS:
            value = getattr(row, knob.key, None) if row is not None else None
            if knob.kind == "list" and not value:
                value = None
            values[knob.key] = knob_default(knob.key) if value is None else value
        return values

    def _knob_schemas(
        self, values: dict[str, Any], *, per_user: bool = False
    ) -> list[CompanionConfigKnobSchema]:
        return [
            CompanionConfigKnobSchema(
                key=knob.key,
                value=values[knob.key],
                default=knob_default(knob.key),
                kind=knob.kind,  # type: ignore[arg-type]
                minimum=knob.minimum,
                maximum=knob.maximum,
                group=knob.group,  # type: ignore[arg-type]
            )
            for knob in KNOBS
            if knob.per_user or not per_user
        ]

    # --- presets ----------------------------------------------------------------

    async def list_presets(self) -> list[CompanionPresetAdminSchema]:
        rows = await self.store.list_presets()
        texts = await self.store.list_preset_texts()
        items = await self.store.list_lore_items()
        counts: dict[str, int] = {}
        for item in items:
            if item.retired_at is None:
                counts[item.preset_id] = counts.get(item.preset_id, 0) + 1
        result: list[CompanionPresetAdminSchema] = []
        known = {row.id for row in rows}
        for row in rows:
            names = {text.locale: text.name for text in texts if text.preset_id == row.id}
            result.append(
                CompanionPresetAdminSchema(
                    id=row.id,
                    position=row.position,
                    enabled=row.enabled,
                    is_global_default=row.is_global_default,
                    names=names or self._seed_names(row.id),
                    fragment_count=counts.get(row.id) or self._seed_count(row.id),
                    admin_modified=row.admin_modified,
                    upstream_changed=_upstream(row),
                    seeded=True,
                )
            )
        for position, preset_id in enumerate(_seed_presets("en")):
            if preset_id in known:
                continue
            result.append(
                CompanionPresetAdminSchema(
                    id=preset_id,
                    position=len(rows) + position,
                    enabled=True,
                    is_global_default=not rows and preset_id == DEFAULT_PRESET_ID,
                    names=self._seed_names(preset_id),
                    fragment_count=self._seed_count(preset_id),
                    admin_modified=False,
                    upstream_changed=False,
                    seeded=False,
                )
            )
        return result

    @staticmethod
    def _seed_names(preset_id: str) -> dict[str, str]:
        names: dict[str, str] = {}
        for locale in LOCALES:
            preset = _seed_preset(preset_id, locale)
            if preset is not None:
                names[locale] = preset.name
        return names

    @staticmethod
    def _seed_count(preset_id: str) -> int:
        preset = _seed_preset(preset_id, "en")
        return len(preset.fragments) if preset else 0

    async def update_preset(
        self, preset_id: str, payload: CompanionPresetAdminUpdateSchema
    ) -> CompanionPresetAdminSchema:
        row = await self._materialize_preset(preset_id)
        if payload.enabled is not None:
            if not payload.enabled and row.is_global_default:
                raise CompanionInvalidError(
                    "Choose another global default before disabling this one."
                )
            row.enabled = payload.enabled
        if payload.position is not None:
            row.position = payload.position
        if payload.is_global_default:
            if not row.enabled:
                raise CompanionInvalidError("A disabled preset cannot be the global default.")
            await self.store.clear_global_default(row.id)
            row.is_global_default = True
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return next(preset for preset in await self.list_presets() if preset.id == preset_id)

    async def get_preset_text(self, preset_id: str, locale: str) -> CompanionPresetTextAdminSchema:
        row = await self.store.get_preset_text(preset_id, locale)
        if row is not None:
            return self._preset_text_schema(row)
        seed = _seed_preset(preset_id, locale) or _seed_preset(preset_id, "en")
        if seed is None:
            raise CompanionRefNotFoundError(f"preset:{preset_id}")
        return CompanionPresetTextAdminSchema(
            preset_id=preset_id,
            locale=locale,  # type: ignore[arg-type]
            name=seed.name,
            persona=seed.persona,
            admin_modified=False,
            upstream_changed=False,
        )

    @staticmethod
    def _preset_text_schema(row: CompanionPresetTextModel) -> CompanionPresetTextAdminSchema:
        return CompanionPresetTextAdminSchema(
            preset_id=row.preset_id,
            locale=row.locale,  # type: ignore[arg-type]
            name=row.name,
            persona=row.persona,
            admin_modified=row.admin_modified,
            upstream_changed=_upstream(row),
            updated_at=row.updated_at,
        )

    async def update_preset_text(
        self, preset_id: str, locale: str, payload: CompanionPresetTextAdminUpdateSchema
    ) -> CompanionPresetTextAdminSchema:
        await self._materialize_preset(preset_id)
        current = await self.get_preset_text(preset_id, locale)
        row = await self.store.get_preset_text(preset_id, locale)
        if row is None:
            row = CompanionPresetTextModel(
                preset_id=preset_id,
                locale=locale,
                name=current.name,
                persona=current.persona,
            )
            await self.store.add(row)
        if payload.name is not None:
            row.name = payload.name.strip()
        if payload.persona is not None:
            row.persona = payload.persona.strip()
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return self._preset_text_schema(row)

    async def reset_preset_text(
        self, preset_id: str, locale: str
    ) -> CompanionPresetTextAdminSchema:
        row = await self.store.get_preset_text(preset_id, locale)
        seed = _seed_preset(preset_id, locale)
        if row is not None:
            if seed is None:
                await self.store.delete(row)
            else:
                row.name = seed.name
                row.persona = seed.persona
                row.admin_modified = False
                row.upstream_seed_hash = None
                row.updated_by_user_id = self.actor_user_id
            await self.store.bump_content_version()
            await self.store.flush()
        return await self.get_preset_text(preset_id, locale)

    # --- lore ------------------------------------------------------------------------

    async def list_lore(
        self,
        *,
        preset_id: str | None,
        locale: str,
        tier: str | None,
        theme: str | None,
        ref: str | None,
        query: str | None,
        origin: str | None,
        upstream_changed: bool | None,
    ) -> list[CompanionLoreItemAdminSchema]:
        rows = await self.store.list_lore_items(preset_id)
        texts = await self.store.list_lore_texts([row.id for row in rows])
        by_item: dict[int, dict[str, CompanionLoreItemTextModel]] = {}
        for text in texts:
            by_item.setdefault(text.item_id, {})[text.locale] = text
        items: list[CompanionLoreItemAdminSchema] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            seen.add((row.preset_id, row.fragment_key))
            localized = by_item.get(row.id, {})
            text_row = localized.get(locale) or localized.get("en")
            items.append(
                CompanionLoreItemAdminSchema(
                    id=row.id,
                    preset_id=row.preset_id,
                    fragment_key=row.fragment_key,
                    tier=row.tier,  # type: ignore[arg-type]
                    themes=list(row.themes),
                    refs=list(row.refs),
                    position=row.position,
                    text=text_row.text if text_row else "",
                    text_locale=(text_row.locale if text_row else "en"),  # type: ignore[arg-type]
                    retired=row.retired_at is not None,
                    admin_modified=row.admin_modified
                    or any(t.admin_modified for t in localized.values()),
                    upstream_changed=_upstream(row)
                    or any(_upstream(t) for t in localized.values()),
                )
            )
        for seed_id, preset in _seed_presets(locale).items():
            if preset_id is not None and seed_id != preset_id:
                continue
            for position, fragment in enumerate(preset.fragments):
                if (seed_id, fragment.key) in seen:
                    continue
                items.append(
                    CompanionLoreItemAdminSchema(
                        id=0,
                        preset_id=seed_id,
                        fragment_key=fragment.key,
                        tier=fragment.tier,
                        themes=list(fragment.themes),
                        refs=list(fragment.refs),
                        position=position,
                        text=fragment.text,
                        text_locale=locale,  # type: ignore[arg-type]
                        retired=False,
                        admin_modified=False,
                        upstream_changed=False,
                    )
                )
        return [
            item
            for item in items
            if (tier is None or item.tier == tier)
            and (theme is None or theme in item.themes)
            and (ref is None or ref in item.refs)
            and (origin is None or (origin == "admin") == item.admin_modified)
            and (upstream_changed is None or item.upstream_changed == upstream_changed)
            and (not query or query.lower() in f"{item.fragment_key} {item.text}".lower())
        ]

    async def _lore_schema(
        self, row: CompanionLoreItemModel, locale: str
    ) -> CompanionLoreItemAdminSchema:
        found = await self.list_lore(
            preset_id=row.preset_id,
            locale=locale,
            tier=None,
            theme=None,
            ref=None,
            query=None,
            origin=None,
            upstream_changed=None,
        )
        return next(item for item in found if item.id == row.id)

    async def _materialize_lore(self, preset_id: str, fragment_key: str) -> CompanionLoreItemModel:
        row = await self.store.find_lore_item(preset_id, fragment_key)
        if row is not None:
            return row
        seed = _seed_preset(preset_id, "en")
        fragment = (
            next((f for f in seed.fragments if f.key == fragment_key), None) if seed else None
        )
        if seed is None or fragment is None:
            raise CompanionLoreNotFoundError(fragment_key)
        await self._materialize_preset(preset_id)
        row = CompanionLoreItemModel(
            preset_id=preset_id,
            fragment_key=fragment_key,
            tier=fragment.tier,
            themes=list(fragment.themes),
            refs=list(fragment.refs),
            position=seed.fragments.index(fragment),
            updated_by_user_id=self.actor_user_id,
        )
        await self.store.add(row)
        for locale in LOCALES:
            localized = _seed_preset(preset_id, locale)
            match = (
                next((f for f in localized.fragments if f.key == fragment_key), None)
                if localized
                else None
            )
            if match is not None and (locale == "en" or match.text != fragment.text):
                await self.store.add(
                    CompanionLoreItemTextModel(item_id=row.id, locale=locale, text=match.text)
                )
        return row

    async def create_lore(
        self, payload: CompanionLoreItemAdminCreateSchema
    ) -> CompanionLoreItemAdminSchema:
        await self._materialize_preset(payload.preset_id)
        if await self.store.find_lore_item(payload.preset_id, payload.fragment_key):
            raise CompanionInvalidError("That fragment key already exists for this preset.")
        seed = _seed_preset(payload.preset_id, "en")
        if seed and any(f.key == payload.fragment_key for f in seed.fragments):
            raise CompanionInvalidError("That fragment key already exists for this preset.")
        existing = await self.store.list_lore_items(payload.preset_id)
        row = CompanionLoreItemModel(
            preset_id=payload.preset_id,
            fragment_key=payload.fragment_key,
            tier=payload.tier,
            themes=list(normalize_themes(payload.themes)),
            refs=[ref.strip() for ref in payload.refs if ref.strip()],
            position=max([r.position for r in existing] + [self._seed_count(payload.preset_id)])
            + 1,
            admin_modified=True,
            updated_by_user_id=self.actor_user_id,
        )
        await self.store.add(row)
        await self.store.add(
            CompanionLoreItemTextModel(
                item_id=row.id,
                locale=payload.locale,
                text=payload.text.strip(),
                admin_modified=True,
                updated_by_user_id=self.actor_user_id,
            )
        )
        await self.store.bump_content_version()
        return await self._lore_schema(row, payload.locale)

    async def _require_lore(self, item_id: int) -> CompanionLoreItemModel:
        row = await self.store.get_lore_item(item_id)
        if row is None:
            raise CompanionLoreNotFoundError(str(item_id))
        return row

    async def resolve_lore_id(self, preset_id: str, fragment_key: str) -> int:
        """Return the database id of a lore item, materializing a seed-only one."""
        return (await self._materialize_lore(preset_id, fragment_key)).id

    async def update_lore(
        self, item_id: int, payload: CompanionLoreItemAdminUpdateSchema
    ) -> CompanionLoreItemAdminSchema:
        row = await self._require_lore(item_id)
        if payload.tier is not None:
            row.tier = payload.tier
        if payload.themes is not None:
            row.themes = list(normalize_themes(payload.themes))
        if payload.refs is not None:
            row.refs = [ref.strip() for ref in payload.refs if ref.strip()]
        if payload.position is not None:
            row.position = payload.position
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        if payload.text is not None:
            text = await self.store.get_lore_text(row.id, payload.locale)
            if text is None:
                text = CompanionLoreItemTextModel(
                    item_id=row.id, locale=payload.locale, text=payload.text.strip()
                )
                await self.store.add(text)
            text.text = payload.text.strip()
            text.admin_modified = True
            text.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return await self._lore_schema(row, payload.locale)

    async def retire_lore(self, item_id: int) -> CompanionLoreItemAdminSchema:
        row = await self._require_lore(item_id)
        row.retired_at = None if row.retired_at is not None else self.clock()
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return await self._lore_schema(row, "en")

    async def reset_lore(self, item_id: int) -> CompanionLoreItemAdminSchema:
        row = await self._require_lore(item_id)
        seed = _seed_preset(row.preset_id, "en")
        fragment = (
            next((f for f in seed.fragments if f.key == row.fragment_key), None) if seed else None
        )
        if fragment is None:
            raise CompanionInvalidError(
                "Only shipped fragments can be reset; retire this one instead."
            )
        row.tier = fragment.tier
        row.themes = list(fragment.themes)
        row.refs = list(fragment.refs)
        row.retired_at = None
        row.admin_modified = False
        row.upstream_seed_hash = None
        for text in await self.store.list_lore_texts([row.id]):
            localized = _seed_preset(row.preset_id, text.locale)
            match = (
                next((f for f in localized.fragments if f.key == row.fragment_key), None)
                if localized
                else None
            )
            if match is None:
                await self.store.delete(text)
            else:
                text.text = match.text
                text.admin_modified = False
                text.upstream_seed_hash = None
        await self.store.bump_content_version()
        await self.store.flush()
        return await self._lore_schema(row, "en")

    # --- world docs and canon ---------------------------------------------------------

    def _doc_keys(self) -> list[str]:
        return [*WORLD_DOC_KEYS, *(f"character:{preset_id}" for preset_id in _seed_presets("en"))]

    async def list_world_docs(self) -> list[CompanionWorldDocSummarySchema]:
        rows = {(row.doc_key, row.locale): row for row in await self.store.list_world_docs()}
        result: list[CompanionWorldDocSummarySchema] = []
        keys = self._doc_keys() + sorted({key for key, _ in rows if key not in self._doc_keys()})
        for doc_key in keys:
            for locale in LOCALES:
                doc = await self.get_world_doc(doc_key, locale, missing_ok=True)
                if doc is None or (doc.locale != locale):
                    continue
                result.append(CompanionWorldDocSummarySchema(**doc.model_dump(exclude={"body_md"})))
        return result

    async def get_world_doc(
        self, doc_key: str, locale: str, *, missing_ok: bool = False
    ) -> CompanionWorldDocSchema | None:
        row = await self.store.get_world_doc(doc_key, locale)
        if row is not None:
            return self._doc_schema(row)
        seed = await self._static.world_doc(doc_key, locale)
        if seed is None or (locale != "en" and self._static._doc_path(doc_key, locale) is None):
            if missing_ok:
                return None
            raise CompanionInvalidError(f"World document {doc_key} ({locale}) does not exist.")
        return CompanionWorldDocSchema(
            doc_key=doc_key,
            locale=locale,  # type: ignore[arg-type]
            kind=seed.kind,
            title=seed.title,
            version=1,
            chars=len(seed.body_md),
            admin_modified=False,
            upstream_changed=False,
            body_md=seed.body_md,
        )

    @staticmethod
    def _doc_schema(row: CompanionWorldDocModel) -> CompanionWorldDocSchema:
        return CompanionWorldDocSchema(
            doc_key=row.doc_key,
            locale=row.locale,  # type: ignore[arg-type]
            kind=row.kind,  # type: ignore[arg-type]
            title=row.title,
            version=row.version,
            chars=len(row.body_md),
            admin_modified=row.admin_modified,
            upstream_changed=_upstream(row),
            updated_at=row.updated_at,
            body_md=row.body_md,
        )

    async def update_world_doc(
        self, doc_key: str, locale: str, payload: CompanionWorldDocUpdateSchema
    ) -> CompanionWorldDocSchema:
        current = await self.get_world_doc(doc_key, locale, missing_ok=True)
        kind = "character" if doc_key.startswith("character:") else doc_key
        if kind not in ("bible", "glossary", "world", "terms", "character"):
            raise CompanionInvalidError("Unknown world document.")
        if current is not None and payload.version != current.version:
            raise CompanionInvalidError(
                "This document changed since you opened it; reload and retry."
            )
        row = await self.store.get_world_doc(doc_key, locale)
        if row is None:
            row = CompanionWorldDocModel(
                doc_key=doc_key,
                locale=locale,
                kind=kind,
                title=(payload.title or (current.title if current else doc_key))[:160],
                body_md=current.body_md if current else payload.body_md,
                version=1,
            )
            await self.store.add(row)
        await self.store.add(
            CompanionWorldDocRevisionModel(
                doc_key=doc_key,
                locale=locale,
                version=row.version,
                body_md=row.body_md,
                created_by_user_id=self.actor_user_id,
            )
        )
        row.body_md = payload.body_md
        if payload.title:
            row.title = payload.title.strip()
        row.version = row.version + 1
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        for stale in (await self.store.list_doc_revisions(doc_key, locale))[REVISIONS_KEPT:]:
            await self.store.delete(stale)
        await self.store.bump_content_version()
        await self.store.flush()
        return self._doc_schema(row)

    async def list_doc_revisions(
        self, doc_key: str, locale: str
    ) -> list[CompanionWorldDocRevisionSchema]:
        return [
            CompanionWorldDocRevisionSchema(
                id=row.id,
                version=row.version,
                body_md=row.body_md,
                created_at=row.created_at,
                created_by_user_id=row.created_by_user_id,
            )
            for row in await self.store.list_doc_revisions(doc_key, locale)
        ]

    async def reset_world_doc(self, doc_key: str, locale: str) -> CompanionWorldDocSchema:
        row = await self.store.get_world_doc(doc_key, locale)
        seed = await self._static.world_doc(doc_key, locale)
        if row is not None and seed is not None:
            await self.store.add(
                CompanionWorldDocRevisionModel(
                    doc_key=doc_key,
                    locale=locale,
                    version=row.version,
                    body_md=row.body_md,
                    created_by_user_id=self.actor_user_id,
                )
            )
            row.body_md = seed.body_md
            row.title = seed.title
            row.version = row.version + 1
            row.admin_modified = False
            row.upstream_seed_hash = None
            await self.store.bump_content_version()
            await self.store.flush()
        doc = await self.get_world_doc(doc_key, locale)
        assert doc is not None
        return doc

    async def list_canon(self, locale: str) -> list[CompanionCanonEntitySchema]:
        rows = {row.entity_id: row for row in await self.store.list_canon(locale)}
        seed = await self._static.canon(locale)
        result = [
            CompanionCanonEntitySchema(
                entity_id=row.entity_id,
                locale=row.locale,  # type: ignore[arg-type]
                name=row.name,
                summary=row.summary,
                admin_modified=row.admin_modified,
            )
            for row in rows.values()
        ]
        result += [
            CompanionCanonEntitySchema(
                entity_id=entry.entity_id,
                locale=locale,  # type: ignore[arg-type]
                name=entry.name,
                summary=entry.summary,
                admin_modified=False,
            )
            for entry in seed.values()
            if entry.entity_id not in rows
        ]
        return sorted(result, key=lambda entity: entity.entity_id)

    async def upsert_canon(
        self, payload: CompanionCanonEntityUpsertSchema
    ) -> CompanionCanonEntitySchema:
        row = await self.store.get_canon(payload.entity_id, payload.locale)
        if row is None:
            row = CompanionCanonEntityModel(
                entity_id=payload.entity_id,
                locale=payload.locale,
                name=payload.name.strip(),
                summary=payload.summary.strip(),
            )
            await self.store.add(row)
        row.name = payload.name.strip()
        row.summary = payload.summary.strip()
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return CompanionCanonEntitySchema(
            entity_id=row.entity_id,
            locale=row.locale,  # type: ignore[arg-type]
            name=row.name,
            summary=row.summary,
            admin_modified=True,
        )

    # --- config and templates ----------------------------------------------------------------

    async def get_config(self) -> CompanionConfigAdminSchema:
        row = await self.store.get_config()
        return CompanionConfigAdminSchema(
            version=row.version if row is not None else 0,
            knobs=self._knob_schemas(await self._effective_config()),
            updated_at=row.updated_at if row is not None else None,
        )

    async def _config_row(self) -> CompanionConfigModel:
        row = await self.store.get_config()
        if row is None:
            row = CompanionConfigModel(id=1)
            await self.store.add(row)
        return row

    async def update_config(
        self, payload: CompanionConfigAdminUpdateSchema
    ) -> CompanionConfigAdminSchema:
        values = {key: coerce_knob(key, value) for key, value in payload.values.items()}
        merged = {**await self._effective_config(), **values}
        if merged["rare_unlock_runs"] < merged["familiar_unlock_runs"]:
            raise CompanionInvalidError("Rare unlocks must not come before familiar unlocks.")
        row = await self._config_row()
        for key, value in values.items():
            setattr(row, key, value)
        row.version = row.version + 1
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.flush()
        return await self.get_config()

    async def reset_config(self) -> CompanionConfigAdminSchema:
        row = await self._config_row()
        for knob in KNOBS:
            setattr(row, knob.key, knob_default(knob.key))
        row.version = row.version + 1
        row.admin_modified = False
        row.updated_by_user_id = self.actor_user_id
        await self.store.flush()
        return await self.get_config()

    @staticmethod
    def _template_default(key: str) -> str:
        return DEFAULT_RUNTIME_CONFIG.template(key, "")

    def _template_schema(
        self,
        key: str,
        locale: str,
        body: str,
        row: CompanionPromptTemplateModel | None,
    ) -> CompanionTemplateAdminSchema:
        required = list(
            row.required_placeholders
            if row is not None and row.required_placeholders
            else REQUIRED_PLACEHOLDERS.get(key, ())
        )
        used = set(placeholders(body))
        return CompanionTemplateAdminSchema(
            template_key=key,
            locale=locale,  # type: ignore[arg-type]
            body=body,
            required_placeholders=required,
            missing_placeholders=[name for name in required if name not in used],
            version=row.version if row is not None else 0,
            admin_modified=row.admin_modified if row is not None else False,
            upstream_changed=_upstream(row) if row is not None else False,
        )

    async def list_templates(self) -> list[CompanionTemplateAdminSchema]:
        rows = {(row.template_key, row.locale): row for row in await self.store.list_templates()}
        result: list[CompanionTemplateAdminSchema] = []
        for key in TEMPLATE_KEYS:
            for locale in LOCALES:
                row = rows.get((key, locale))
                if row is None and locale != "en":
                    continue
                body = row.body if row is not None else self._template_default(key)
                result.append(self._template_schema(key, locale, body, row))
        return result

    async def update_template(
        self, key: str, locale: str, payload: CompanionTemplateAdminUpdateSchema
    ) -> CompanionTemplateAdminSchema:
        if key not in TEMPLATE_KEYS:
            raise CompanionInvalidError("Unknown template.")
        required = REQUIRED_PLACEHOLDERS.get(key, ())
        missing = [name for name in required if name not in placeholders(payload.body)]
        if missing:
            raise CompanionInvalidError(
                f"The template must keep these placeholders: {', '.join(missing)}."
            )
        row = await self.store.get_template(key, locale)
        if row is None:
            row = CompanionPromptTemplateModel(
                template_key=key,
                locale=locale,
                body=payload.body,
                required_placeholders=list(required),
                version=1,
                admin_modified=True,
            )
            await self.store.add(row)
        else:
            row.version = row.version + 1
        row.body = payload.body
        row.admin_modified = True
        row.updated_by_user_id = self.actor_user_id
        await self.store.bump_content_version()
        await self.store.flush()
        return self._template_schema(key, locale, row.body, row)

    async def reset_template(self, key: str, locale: str) -> CompanionTemplateAdminSchema:
        row = await self.store.get_template(key, locale)
        default = self._template_default(key)
        if row is not None:
            if locale != "en" or not default:
                await self.store.delete(row)
                row = None
            else:
                row.body = default
                row.version = row.version + 1
                row.admin_modified = False
                row.upstream_seed_hash = None
            await self.store.bump_content_version()
            await self.store.flush()
        return self._template_schema(key, locale, row.body if row else default, row)

    async def preview_template(
        self, payload: CompanionTemplatePreviewRequestSchema
    ) -> CompanionTemplatePreviewSchema:
        if payload.body is not None:
            body = payload.body
        else:
            row = await self.store.get_template(payload.template_key, payload.locale)
            body = row.body if row is not None else self._template_default(payload.template_key)
        used = placeholders(body)
        required = REQUIRED_PLACEHOLDERS.get(payload.template_key, ())
        return CompanionTemplatePreviewSchema(
            rendered=render_sample(body),
            missing_placeholders=[name for name in required if name not in used],
            unknown_placeholders=[name for name in used if name not in SAMPLE_VALUES],
        )

    # --- seed ------------------------------------------------------------------------------------

    async def seed_status(self) -> CompanionSeedStatusSchema:
        state = await self.store.get_seed_state()
        modified, upstream = await self.store.count_seed_flags()
        presets = _seed_presets("en")
        return CompanionSeedStatusSchema(
            applied=state is not None,
            seed_version=state.seed_version if state else None,
            content_version=state.content_version if state else None,
            applied_at=state.applied_at if state else None,
            shipped_presets=len(presets),
            shipped_fragments=sum(len(preset.fragments) for preset in presets.values()),
            database_presets=len(await self.store.list_presets()),
            database_fragments=len(await self.store.list_lore_items()),
            admin_modified_rows=modified,
            upstream_changed_rows=upstream,
        )

    async def apply_seed(self, payload: CompanionSeedApplySchema) -> CompanionSeedStatusSchema:
        if self.seeder is None:
            raise CompanionInvalidError("The seed bundle cannot be applied from this process yet.")
        await self.seeder.apply(force_keys=payload.force_keys)
        return await self.seed_status()

    # --- accounts ------------------------------------------------------------------------------

    async def list_user_summaries(self) -> list[CompanionUserSummarySchema]:
        accounts = await self.store.list_accounts()
        bonds = await self.store.list_bonds()
        told = await self.store.list_told()
        generated = await self.store.list_generated()
        preferences = {row.user_id: row for row in await self.store.list_preferences()}
        now = self.clock()
        result: list[CompanionUserSummarySchema] = []
        for account in accounts:
            own_bonds = [bond for bond in bonds if bond.user_id == account.id]
            own_told = [row for row in told if row.user_id == account.id]
            weeks = recent_weeks(now, (row.last_told_at for row in own_told))
            stamps = [row.last_told_at for row in own_told] + [b.updated_at for b in own_bonds]
            preference = preferences.get(account.id)
            result.append(
                CompanionUserSummarySchema(
                    user_id=account.id,
                    username=account.username,
                    display_name=account.display_name,
                    role=account.role,
                    is_active=account.is_active,
                    active_ref=preference.selected if preference else None,
                    enabled=preference.enabled if preference else True,
                    completed_runs=sum(bond.completed_runs for bond in own_bonds),
                    told_count=len(own_told),
                    generated_count=sum(1 for story in generated if story.user_id == account.id),
                    last_activity_at=max(stamps) if stamps else None,
                    activity=weeks,
                )
            )
        return result

    def _policy_value(self, row: CompanionAccountPolicyModel | None) -> AccountCompanionPolicy:
        if row is None:
            return AccountCompanionPolicy()
        return AccountCompanionPolicy(
            default_ref=row.default_ref,
            allowed_refs=tuple(row.allowed_refs) if row.allowed_refs is not None else None,
            allow_custom=row.allow_custom,
            pinned_ref=row.pinned_ref,
            pin_enabled=row.pin_enabled,
        )

    async def get_policy(self, user_id: int) -> CompanionPolicyAdminSchema:
        await self._account(user_id)
        row = await self.store.get_policy(user_id)
        policy = self._policy_value(row)
        presets = await self._preset_ids()
        customs = await self._custom_refs(user_id)
        preference = await self.store.get_preference(user_id)
        selected = preference.selected if preference else None
        if selected and not selected.startswith(("preset:", "custom:")):
            selected = f"preset:{selected}" if selected in presets else selected
        choice = resolve_active_companion(
            user_selected=selected,
            policy=policy,
            global_default=await self._global_default(),
            enabled_presets=presets,
            custom_refs=customs,
        )
        return CompanionPolicyAdminSchema(
            user_id=user_id,
            default_ref=policy.default_ref,
            allowed_refs=list(policy.allowed_refs) if policy.allowed_refs is not None else None,
            allow_custom=policy.allow_custom,
            pinned_ref=policy.pinned_ref,
            pin_enabled=policy.pin_enabled,
            options=[*(f"preset:{p}" for p in presets), *customs],
            active_ref=choice.ref,
            active_source=choice.source,
            user_selected=selected,
            updated_at=row.updated_at if row is not None else None,
        )

    async def update_policy(
        self, user_id: int, payload: CompanionPolicyAdminUpdateSchema
    ) -> CompanionPolicyAdminSchema:
        await self._account(user_id)
        options = set((await self.get_policy(user_id)).options)
        for ref in [payload.default_ref, payload.pinned_ref, *(payload.allowed_refs or [])]:
            if ref is not None and ref not in options:
                raise CompanionInvalidError(f"{ref} is not a companion this account can have.")
        if payload.pin_enabled and not payload.pinned_ref:
            raise CompanionInvalidError("Choose a companion to pin.")
        row = await self.store.get_policy(user_id)
        if row is None:
            row = CompanionAccountPolicyModel(user_id=user_id)
            await self.store.add(row)
        row.default_ref = payload.default_ref
        row.allowed_refs = (
            list(dict.fromkeys(payload.allowed_refs)) if payload.allowed_refs is not None else None
        )
        row.allow_custom = payload.allow_custom
        row.pinned_ref = payload.pinned_ref
        row.pin_enabled = payload.pin_enabled
        await self.store.flush()
        await self._log(user_id, "override")
        return await self.get_policy(user_id)

    async def _user_config_values(self, user_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        base = await self._effective_config()
        row = await self.store.get_user_config(user_id)
        overrides = {
            knob.key: getattr(row, knob.key, None) if row is not None else None
            for knob in KNOBS
            if knob.per_user
        }
        merged = {**base, **{k: v for k, v in overrides.items() if v is not None}}
        return merged, overrides

    async def _bond_schema(
        self, user_id: int, bond: CompanionBondModel, config: dict[str, Any]
    ) -> CompanionBondAdminSchema:
        told = await self.store.list_told(user_id, bond.companion_ref)
        generated = await self.store.list_generated(user_id, bond.companion_ref)
        every = int(config["story_moment_every_runs"])
        next_moment: int | None = None
        if every > 0:
            since = bond.completed_runs - (bond.last_story_run or 0)
            next_moment = (
                max(0, every - since)
                if bond.last_story_run is not None
                else max(0, 1 - bond.completed_runs)
            )
        every_conv = int(config["life_story_every_conversations"])
        next_life = (
            max(0, every_conv - (bond.conversations - bond.last_life_story_conversations))
            if config["life_story_enabled"]
            else None
        )
        fragments = await self.user_fragments(user_id, bond.companion_ref, "en", log=False)
        return CompanionBondAdminSchema(
            companion_ref=bond.companion_ref,
            name=await self._ref_name(bond.companion_ref, user_id),
            completed_runs=bond.completed_runs,
            conversations=bond.conversations,
            familiar_unlocked_at=bond.familiar_unlocked_at,
            rare_unlocked_at=bond.rare_unlocked_at,
            last_story_run=bond.last_story_run,
            next_story_moment_in_runs=next_moment,
            next_life_story_in_conversations=next_life,
            told_count=sum(1 for row in told if row.told_count > 0),
            fragment_count=len(fragments.fragments),
            generated_count=len(generated),
            admin_adjusted_at=bond.admin_adjusted_at,
        )

    async def get_user(self, user_id: int) -> CompanionUserAdminSchema:
        account = await self._account(user_id)
        policy = await self.get_policy(user_id)
        config, _ = await self._user_config_values(user_id)
        bonds = {bond.companion_ref: bond for bond in await self.store.list_bonds(user_id)}
        if policy.active_ref not in bonds:
            bonds[policy.active_ref] = CompanionBondModel(
                user_id=user_id,
                companion_ref=policy.active_ref,
                completed_runs=0,
                conversations=0,
                last_life_story_conversations=0,
            )
        ordered = sorted(
            bonds.values(), key=lambda b: (b.companion_ref != policy.active_ref, b.companion_ref)
        )
        return CompanionUserAdminSchema(
            user_id=user_id,
            username=account.username,
            display_name=account.display_name,
            policy=policy,
            bonds=[await self._bond_schema(user_id, bond, config) for bond in ordered],
            custom_companions=await self._custom_refs(user_id),
        )

    async def get_user_config(self, user_id: int) -> CompanionUserConfigAdminSchema:
        await self._account(user_id)
        merged, overrides = await self._user_config_values(user_id)
        row = await self.store.get_user_config(user_id)
        return CompanionUserConfigAdminSchema(
            user_id=user_id,
            knobs=self._knob_schemas(merged, per_user=True),
            overrides=overrides,
            updated_at=row.updated_at if row is not None else None,
        )

    async def update_user_config(
        self, user_id: int, payload: CompanionUserConfigAdminUpdateSchema
    ) -> CompanionUserConfigAdminSchema:
        await self._account(user_id)
        values: dict[str, Any] = {}
        for key, value in payload.values.items():
            knob = _KNOB_BY_KEY.get(key)
            if knob is None or not knob.per_user:
                raise CompanionInvalidError(f"{key} cannot be set per account.")
            values[key] = None if value is None else coerce_knob(key, value)
        row = await self.store.get_user_config(user_id)
        if row is None:
            row = CompanionUserConfigModel(user_id=user_id)
            await self.store.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        merged, _ = await self._user_config_values(user_id)
        if merged["rare_unlock_runs"] < merged["familiar_unlock_runs"]:
            raise CompanionInvalidError("Rare unlocks must not come before familiar unlocks.")
        await self.store.flush()
        await self._log(user_id, "override")
        return await self.get_user_config(user_id)

    async def reset_user_config(self, user_id: int) -> CompanionUserConfigAdminSchema:
        await self._account(user_id)
        row = await self.store.get_user_config(user_id)
        if row is not None:
            await self.store.delete(row)
            await self._log(user_id, "override")
        return await self.get_user_config(user_id)

    # --- per-account story ---------------------------------------------------------------

    async def _preset_items(self, preset_id: str, locale: str) -> tuple[StoryItem, ...]:
        rows = [
            row for row in await self.store.list_lore_items(preset_id) if row.retired_at is None
        ]
        db_keys = {row.fragment_key for row in await self.store.list_lore_items(preset_id)}
        texts: dict[int, dict[str, str]] = {}
        for text in await self.store.list_lore_texts([row.id for row in rows]):
            texts.setdefault(text.item_id, {})[text.locale] = text.text
        items = [
            StoryItem(
                key=row.fragment_key,
                text=texts.get(row.id, {}).get(locale) or texts.get(row.id, {}).get("en", ""),
                themes=tuple(row.themes),
                tier=row.tier,  # type: ignore[arg-type]
                refs=tuple(row.refs),
                origin="preset",
            )
            for row in sorted(rows, key=lambda r: (r.position, r.fragment_key))
        ]
        seed = _seed_preset(preset_id, locale)
        if seed is not None:
            items += [fragment for fragment in seed.fragments if fragment.key not in db_keys]
        return tuple(items)

    async def user_fragments(
        self, user_id: int, companion_ref: str, locale: str, *, log: bool = True
    ) -> CompanionUserFragmentsSchema:
        del log
        preset_id = _ref_preset(companion_ref)
        custom_id = _ref_custom(companion_ref)
        if preset_id is None and custom_id is None:
            raise CompanionRefNotFoundError(companion_ref)
        preset_items = await self._preset_items(preset_id, locale) if preset_id else ()
        override_rows = await self.store.list_lore_overrides(user_id, companion_ref, locale)
        overrides = tuple(
            AdminLoreOverride(
                key=row.fragment_key,
                action=row.action,  # type: ignore[arg-type]
                item=(
                    StoryItem(
                        key=row.fragment_key,
                        text=row.text or "",
                        themes=tuple(row.themes),
                        tier=(row.tier or "first"),  # type: ignore[arg-type]
                        refs=tuple(row.refs),
                        origin="admin",
                    )
                    if row.action != "hide"
                    else None
                ),
                position=row.position,
            )
            for row in override_rows
        )
        story = await self.store.get_user_story(
            user_id, preset_id=preset_id, companion_id=custom_id, locale=locale
        )
        user_items: tuple[StoryItem, ...] | None = None
        if story is not None and (story.lore_customized or custom_id is not None):
            user_items = tuple(
                StoryItem(
                    key=row.fragment_key,
                    text=row.text,
                    themes=tuple(row.themes),
                    tier=row.tier,  # type: ignore[arg-type]
                    refs=tuple(row.refs),
                    edited=row.edited,
                    origin="user",
                )
                for row in await self.store.list_user_fragments(user_id, story.id)
            )
        generated_rows = [
            row
            for row in await self.store.list_generated(user_id, companion_ref)
            if row.status == "published"
        ]
        generated = tuple(
            StoryItem(
                key=row.fragment_key,
                text=row.text,
                themes=tuple(row.themes),
                tier=row.tier,  # type: ignore[arg-type]
                origin="generated",
            )
            for row in generated_rows
        )
        effective = resolve_story_items(
            StoryLayers(
                preset_items=preset_items,
                admin_overrides=overrides,
                user_items=user_items,
                generated_items=generated,
            )
        )
        hidden = {row.fragment_key for row in override_rows if row.action == "hide"}
        bond = await self.store.get_bond(user_id, companion_ref)
        config, _ = await self._user_config_values(user_id)
        tiers = unlocked_tiers(
            bond.completed_runs if bond else 0,
            DEFAULT_RUNTIME_CONFIG.__class__(
                familiar_unlock_runs=int(config["familiar_unlock_runs"]),
                rare_unlock_runs=int(config["rare_unlock_runs"]),
            ),
        )
        told = {row.fragment_key: row for row in await self.store.list_told(user_id, companion_ref)}
        fragments: list[CompanionUserFragmentSchema] = []
        for item in effective:
            record = told.get(item.key)
            state = (
                "told"
                if record is not None and record.told_count > 0
                else ("unlocked" if item.tier in tiers else "locked")
            )
            fragments.append(
                CompanionUserFragmentSchema(
                    key=item.key,
                    origin=item.origin,
                    tier=item.tier,
                    themes=list(item.themes),
                    refs=list(item.refs),
                    text=item.text,
                    state=state,  # type: ignore[arg-type]
                    told_count=record.told_count if record else 0,
                    offered_at=record.offered_at if record else None,
                    last_told_at=record.last_told_at if record else None,
                    source=record.source if record else None,  # type: ignore[arg-type]
                )
            )
        for key in sorted(hidden):
            match = next((item for item in preset_items if item.key == key), None)
            if match is not None:
                fragments.append(
                    CompanionUserFragmentSchema(
                        key=key,
                        origin="preset",
                        tier=match.tier,
                        themes=list(match.themes),
                        refs=list(match.refs),
                        text=match.text,
                        state="locked",
                        told_count=0,
                        hidden_by_admin=True,
                    )
                )
        return CompanionUserFragmentsSchema(
            user_id=user_id,
            companion_ref=companion_ref,
            locale=locale,  # type: ignore[arg-type]
            unlocked_tiers=sorted(tiers, key=_TIERS.index),  # type: ignore[arg-type]
            fragments=fragments,
        )

    async def update_bond(
        self, user_id: int, companion_ref: str, payload: CompanionBondAdminUpdateSchema
    ) -> CompanionUserAdminSchema:
        await self._account(user_id)
        bond = await self.store.get_bond(user_id, companion_ref)
        now = self.clock()
        if bond is None:
            bond = CompanionBondModel(
                user_id=user_id,
                companion_ref=companion_ref,
                completed_runs=0,
                conversations=0,
                last_life_story_conversations=0,
            )
            await self.store.add(bond)
        config, _ = await self._user_config_values(user_id)
        if payload.completed_runs is not None:
            bond.completed_runs = payload.completed_runs
            if bond.completed_runs >= int(config["familiar_unlock_runs"]):
                bond.familiar_unlocked_at = bond.familiar_unlocked_at or now
            else:
                bond.familiar_unlocked_at = None
            if bond.completed_runs >= int(config["rare_unlock_runs"]):
                bond.rare_unlocked_at = bond.rare_unlocked_at or now
            else:
                bond.rare_unlocked_at = None
        if payload.conversations is not None:
            bond.conversations = payload.conversations
            bond.last_life_story_conversations = min(
                bond.last_life_story_conversations, payload.conversations
            )
        bond.admin_adjusted_at = now
        await self.store.flush()
        await self._log(user_id, "adjust_progress", companion_ref=companion_ref)
        return await self.get_user(user_id)

    async def set_fragment_progress(
        self, user_id: int, companion_ref: str, payload: CompanionFragmentProgressUpdateSchema
    ) -> CompanionUserFragmentsSchema:
        await self._account(user_id)
        if payload.told:
            record = await self.store.get_told(user_id, companion_ref, payload.fragment_key)
            now = self.clock()
            if record is None:
                await self.store.add(
                    CompanionLoreToldModel(
                        user_id=user_id,
                        companion_ref=companion_ref,
                        fragment_key=payload.fragment_key,
                        told_count=1,
                        source="admin",
                        offered_at=now,
                        last_told_at=now,
                    )
                )
            else:
                record.told_count = max(1, record.told_count)
                record.last_told_at = now
                await self.store.flush()
        else:
            await self.store.delete_told(user_id, companion_ref, payload.fragment_key)
        await self._log(user_id, "adjust_progress", companion_ref=companion_ref)
        return await self.user_fragments(user_id, companion_ref, "en")

    async def reset_progress(
        self, user_id: int, companion_ref: str, payload: CompanionProgressResetSchema
    ) -> CompanionUserAdminSchema:
        await self._account(user_id)
        if payload.scope in ("told", "all"):
            await self.store.delete_told(user_id, companion_ref)
        if payload.scope in ("bond", "all"):
            bond = await self.store.get_bond(user_id, companion_ref)
            if bond is not None:
                bond.completed_runs = 0
                bond.conversations = 0
                bond.last_story_run = None
                bond.last_life_story_conversations = 0
                bond.familiar_unlocked_at = None
                bond.rare_unlocked_at = None
                bond.admin_adjusted_at = self.clock()
                await self.store.flush()
        await self._log(user_id, "reset_progress", companion_ref=companion_ref)
        return await self.get_user(user_id)

    async def _inherited_persona(self, user_id: int, companion_ref: str, locale: str) -> str:
        preset_id = _ref_preset(companion_ref)
        name = await self._ref_name(companion_ref, user_id, locale)
        if preset_id is None:
            return default_custom_persona(name)
        text = await self.store.get_preset_text(preset_id, locale)
        english = await self.store.get_preset_text(preset_id, "en")
        seed = _seed_preset(preset_id, locale)
        seed_en = _seed_preset(preset_id, "en")
        return resolve_persona(
            user_persona=None,
            admin_persona=None,
            preset_persona=(text.persona if text else seed.persona if seed else None),
            english_preset_persona=(
                english.persona if english else seed_en.persona if seed_en else None
            ),
            fallback=default_custom_persona(name),
        )

    async def get_persona_override(
        self, user_id: int, companion_ref: str, locale: str
    ) -> CompanionPersonaOverrideSchema:
        await self._account(user_id)
        row = await self.store.get_persona_override(user_id, companion_ref, locale)
        return CompanionPersonaOverrideSchema(
            user_id=user_id,
            companion_ref=companion_ref,
            locale=locale,  # type: ignore[arg-type]
            persona=row.persona if row is not None else None,
            inherited_persona=await self._inherited_persona(user_id, companion_ref, locale),
            updated_at=row.updated_at if row is not None else None,
        )

    async def update_persona_override(
        self,
        user_id: int,
        companion_ref: str,
        locale: str,
        payload: CompanionPersonaOverrideUpdateSchema,
    ) -> CompanionPersonaOverrideSchema:
        await self._account(user_id)
        row = await self.store.get_persona_override(user_id, companion_ref, locale)
        if row is None:
            row = CompanionAdminStoryOverrideModel(
                user_id=user_id,
                companion_ref=companion_ref,
                locale=locale,
                persona=payload.persona.strip(),
            )
            await self.store.add(row)
        row.persona = payload.persona.strip()
        await self.store.flush()
        await self._log(user_id, "override", companion_ref=companion_ref)
        return await self.get_persona_override(user_id, companion_ref, locale)

    async def reset_persona_override(
        self, user_id: int, companion_ref: str, locale: str
    ) -> CompanionPersonaOverrideSchema:
        await self._account(user_id)
        row = await self.store.get_persona_override(user_id, companion_ref, locale)
        if row is not None:
            await self.store.delete(row)
            await self._log(user_id, "override", companion_ref=companion_ref)
        return await self.get_persona_override(user_id, companion_ref, locale)

    @staticmethod
    def _override_schema(row: CompanionAdminLoreOverrideModel) -> CompanionLoreOverrideSchema:
        return CompanionLoreOverrideSchema(
            fragment_key=row.fragment_key,
            action=row.action,  # type: ignore[arg-type]
            text=row.text,
            tier=row.tier,  # type: ignore[arg-type]
            themes=list(row.themes),
            refs=list(row.refs),
            position=row.position,
            updated_at=row.updated_at,
        )

    async def list_lore_overrides(
        self, user_id: int, companion_ref: str, locale: str
    ) -> list[CompanionLoreOverrideSchema]:
        await self._account(user_id)
        return [
            self._override_schema(row)
            for row in await self.store.list_lore_overrides(user_id, companion_ref, locale)
        ]

    async def upsert_lore_override(
        self,
        user_id: int,
        companion_ref: str,
        locale: str,
        payload: CompanionLoreOverrideUpsertSchema,
    ) -> CompanionLoreOverrideSchema:
        await self._account(user_id)
        if payload.action != "hide" and not (payload.text and payload.text.strip()):
            raise CompanionInvalidError("Replace and add overrides need text.")
        if payload.action == "add" and payload.tier is None:
            raise CompanionInvalidError("Added fragments need a tier.")
        row = await self.store.get_lore_override(
            user_id, companion_ref, locale, payload.fragment_key
        )
        is_new = row is None
        if row is None:
            row = CompanionAdminLoreOverrideModel(
                user_id=user_id,
                companion_ref=companion_ref,
                locale=locale,
                fragment_key=payload.fragment_key,
            )
        row.action = payload.action
        row.text = payload.text.strip() if payload.text else None
        row.tier = payload.tier
        row.themes = list(normalize_themes(payload.themes))
        row.refs = [ref.strip() for ref in payload.refs if ref.strip()]
        row.position = payload.position
        if is_new:
            await self.store.add(row)
        else:
            await self.store.flush()
        await self._log(user_id, "override", companion_ref=companion_ref)
        return self._override_schema(row)

    async def delete_lore_override(
        self, user_id: int, companion_ref: str, locale: str, fragment_key: str
    ) -> None:
        await self._account(user_id)
        row = await self.store.get_lore_override(user_id, companion_ref, locale, fragment_key)
        if row is None:
            raise CompanionLoreNotFoundError(fragment_key)
        await self.store.delete(row)
        await self._log(user_id, "override", companion_ref=companion_ref)

    # --- generated stories and jobs ----------------------------------------------------------

    async def _story_told(self, user_id: int, story: CompanionGeneratedStoryModel) -> int:
        record = await self.store.get_told(user_id, story.companion_ref, story.fragment_key)
        return record.told_count if record else 0

    async def _story_summary(
        self, user_id: int, story: CompanionGeneratedStoryModel
    ) -> CompanionGeneratedStorySummarySchema:
        return CompanionGeneratedStorySummarySchema(
            id=story.id,
            companion_ref=story.companion_ref,
            locale=story.locale,  # type: ignore[arg-type]
            title=story.title,
            status=story.status,  # type: ignore[arg-type]
            tier=story.tier,  # type: ignore[arg-type]
            chars=len(story.text),
            model=story.model,
            source_counts=_source_counts(story.source_refs),
            told_count=await self._story_told(user_id, story),
            admin_edited_at=story.admin_edited_at,
            created_at=story.created_at,
        )

    async def list_stories(self, user_id: int) -> list[CompanionGeneratedStorySummarySchema]:
        await self._account(user_id)
        return [
            await self._story_summary(user_id, story)
            for story in await self.store.list_generated(user_id)
        ]

    async def _require_story(self, user_id: int, story_id: int) -> CompanionGeneratedStoryModel:
        story = await self.store.get_generated(user_id, story_id)
        if story is None:
            raise CompanionLoreNotFoundError(f"g-{story_id}")
        return story

    async def _story_full(
        self, user_id: int, story: CompanionGeneratedStoryModel
    ) -> CompanionGeneratedStorySchema:
        summary = await self._story_summary(user_id, story)
        return CompanionGeneratedStorySchema(
            **summary.model_dump(),
            text=story.text,
            themes=list(story.themes),
            prompt_tokens=story.prompt_tokens,
            completion_tokens=story.completion_tokens,
            template_version=story.template_version,
        )

    async def get_story(self, user_id: int, story_id: int) -> CompanionGeneratedStorySchema:
        story = await self._require_story(user_id, story_id)
        await self._log(
            user_id, "view_full_text", story_id=story.id, companion_ref=story.companion_ref
        )
        return await self._story_full(user_id, story)

    async def update_story(
        self, user_id: int, story_id: int, payload: CompanionGeneratedStoryUpdateSchema
    ) -> CompanionGeneratedStorySchema:
        story = await self._require_story(user_id, story_id)
        if payload.title is not None:
            story.title = payload.title.strip()
        if payload.text is not None:
            story.text = payload.text.strip()
        if payload.tier is not None:
            story.tier = payload.tier
        if payload.status is not None:
            story.status = payload.status
        story.admin_edited_at = self.clock()
        await self.store.flush()
        await self._log(user_id, "edit", story_id=story.id, companion_ref=story.companion_ref)
        return await self._story_full(user_id, story)

    async def delete_story(self, user_id: int, story_id: int) -> None:
        story = await self._require_story(user_id, story_id)
        companion_ref = story.companion_ref
        await self.store.delete_told(user_id, companion_ref, story.fragment_key)
        await self.store.delete(story)
        await self._log(user_id, "delete", story_id=story_id, companion_ref=companion_ref)

    async def _queue_job(
        self,
        user_id: int,
        companion_ref: str,
        locale: str,
        *,
        trigger: str,
        replaces_story_id: int | None = None,
    ) -> CompanionStoryJobModel:
        if await self.store.active_job(user_id, companion_ref) is not None:
            raise CompanionInvalidError("A story is already being written for this companion.")
        now = self.clock()
        job = CompanionStoryJobModel(
            user_id=user_id,
            companion_ref=companion_ref,
            locale=locale,
            trigger=trigger,
            trigger_key=f"{trigger}:{companion_ref}:{now.isoformat()}",
            replaces_story_id=replaces_story_id,
            status="queued",
            attempts=0,
            not_before=now,
        )
        await self.store.add(job)
        return job

    async def regenerate_story(self, user_id: int, story_id: int) -> CompanionStoryJobSchema:
        story = await self._require_story(user_id, story_id)
        job = await self._queue_job(
            user_id,
            story.companion_ref,
            story.locale,
            trigger="regenerate",
            replaces_story_id=story.id,
        )
        await self._log(user_id, "regenerate", story_id=story.id, companion_ref=story.companion_ref)
        return self._job_schema(job)

    async def generate_story(
        self, user_id: int, payload: CompanionStoryGenerateSchema
    ) -> CompanionStoryJobSchema:
        await self._account(user_id)
        options = set((await self.get_policy(user_id)).options)
        if payload.companion_ref not in options:
            raise CompanionRefNotFoundError(payload.companion_ref)
        job = await self._queue_job(user_id, payload.companion_ref, payload.locale, trigger="admin")
        await self._log(user_id, "generate", companion_ref=payload.companion_ref)
        return self._job_schema(job)

    @staticmethod
    def _job_schema(job: CompanionStoryJobModel) -> CompanionStoryJobSchema:
        return CompanionStoryJobSchema(
            id=job.id,
            companion_ref=job.companion_ref,
            locale=job.locale,  # type: ignore[arg-type]
            trigger=job.trigger,  # type: ignore[arg-type]
            status=job.status,  # type: ignore[arg-type]
            skip_reason=job.skip_reason,
            error_code=job.error_code,
            attempts=job.attempts,
            replaces_story_id=job.replaces_story_id,
            created_at=job.created_at,
            finished_at=job.finished_at,
        )

    async def list_jobs(self, user_id: int) -> list[CompanionStoryJobSchema]:
        await self._account(user_id)
        return [self._job_schema(job) for job in await self.store.list_jobs(user_id)]

    async def cancel_job(self, user_id: int, job_id: int) -> CompanionStoryJobSchema:
        job = await self.store.get_job(user_id, job_id)
        if job is None:
            raise CompanionLoreNotFoundError(f"job-{job_id}")
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = self.clock()
        elif job.status == "running":
            job.status = "cancel_requested"
        await self.store.flush()
        await self._log(user_id, "edit", companion_ref=job.companion_ref)
        return self._job_schema(job)

    async def list_access(self, user_id: int) -> list[CompanionAccessLogSchema]:
        await self._account(user_id)
        return [
            CompanionAccessLogSchema(
                id=row.id,
                actor_user_id=row.actor_user_id,
                story_id=row.story_id,
                companion_ref=row.companion_ref,
                action=row.action,
                at=row.at,
            )
            for row in await self.store.list_access(user_id)
        ]


def recent_weeks(
    now: datetime, stamps: Iterable[datetime], weeks: int = ACTIVITY_WEEKS
) -> list[int]:
    """Bucket timestamps into ``weeks`` weekly counts, oldest first."""
    buckets = [0] * weeks
    for stamp in stamps:
        age = (now - stamp) // timedelta(days=7)
        if 0 <= age < weeks:
            buckets[weeks - 1 - age] += 1
    return buckets


class CompanionCatalogService:
    """The account's own view: which presets it may choose and who is active."""

    def __init__(self, store: CompanionAdminStoreProtocol, *, user_id: int) -> None:
        self.store = store
        self.user_id = user_id
        self._static = StaticCompanionContentProvider()

    async def catalog(self, locale: str) -> CompanionPresetCatalogSchema:
        rows = await self.store.list_presets()
        if rows:
            ordered = [(row.id, row.position) for row in rows if row.enabled]
            default = next(
                (f"preset:{r.id}" for r in rows if r.is_global_default and r.enabled), None
            )
        else:
            ordered = [(pid, i) for i, pid in enumerate(await self._static.enabled_preset_ids())]
            default = None
        default = default or f"preset:{await self._static.global_default_preset_id()}"
        policy_row = await self.store.get_policy(self.user_id)
        policy = (
            AccountCompanionPolicy(
                default_ref=policy_row.default_ref,
                allowed_refs=tuple(policy_row.allowed_refs)
                if policy_row.allowed_refs is not None
                else None,
                allow_custom=policy_row.allow_custom,
                pinned_ref=policy_row.pinned_ref,
                pin_enabled=policy_row.pin_enabled,
            )
            if policy_row is not None
            else AccountCompanionPolicy()
        )
        preset_ids = [preset_id for preset_id, _ in ordered]
        customs = [
            f"custom:{row.id}" for row in await self.store.list_custom_companions(self.user_id)
        ]
        options = allowed_refs(policy, enabled_presets=preset_ids, custom_refs=customs)
        preference = await self.store.get_preference(self.user_id)
        selected = preference.selected if preference else None
        if selected and not selected.startswith(("preset:", "custom:")):
            selected = f"preset:{selected}"
        choice = resolve_active_companion(
            user_selected=selected,
            policy=policy,
            global_default=default,
            enabled_presets=preset_ids,
            custom_refs=customs,
        )
        texts = {(t.preset_id, t.locale): t.name for t in await self.store.list_preset_texts()}
        presets: list[CompanionPresetOptionSchema] = []
        for preset_id, position in ordered:
            ref = f"preset:{preset_id}"
            if ref not in options and ref != choice.ref:
                continue
            seed = _seed_preset(preset_id, locale) or _seed_preset(preset_id, "en")
            name = (
                texts.get((preset_id, locale))
                or texts.get((preset_id, "en"))
                or (seed.name if seed else preset_id)
            )
            presets.append(
                CompanionPresetOptionSchema(id=preset_id, ref=ref, name=name, position=position)
            )
        return CompanionPresetCatalogSchema(
            presets=presets,
            allowed_refs=list(options),
            allow_custom=policy.allow_custom,
            active_ref=choice.ref,
            active_source=choice.source,
            pinned=choice.pinned,
        )


__all__ = [
    "KNOBS",
    "CompanionAdminService",
    "CompanionCatalogService",
    "coerce_knob",
    "knob_default",
    "placeholders",
    "recent_weeks",
    "render_sample",
]
