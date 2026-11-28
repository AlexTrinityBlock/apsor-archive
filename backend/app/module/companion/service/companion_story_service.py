"""Companion stories: persona and lore editing, the active persona, and bonds.

Presets ship a default story per locale (English canonical, translations
falling back per item). An account edits one locale of a preset copy-on-write:
the first lore edit copies that locale's defaults into owner rows, and reset
deletes the copy. A custom companion has no shipped default; its rows are the
story, falling back from the requested locale to English and then to any
locale the owner wrote.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from app.module.companion.domain.companion_domain import (
    CompanionSelection,
    parse_selection,
)
from app.module.companion.domain.story_domain import (
    DEFAULT_PRESET_ID,
    DEFAULT_STORY_CONFIG,
    MAX_FRAGMENTS_PER_COMPANION,
    Bond,
    CompanionStoryConfig,
    LoreFragment,
    LoreTier,
    StoryLocale,
    ToldRecord,
    default_custom_persona,
    normalize_themes,
)
from app.module.companion.exception.domain_error import (
    CompanionLoreLimitError,
    CompanionLoreNotFoundError,
    CompanionRefNotFoundError,
)
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionStoryModel,
)
from app.module.companion.protocol.companion_story_protocol import (
    CompanionLookupProtocol,
    CompanionStoryRepositoryProtocol,
)
from app.module.companion.protocol.life_story_protocol import GeneratedStorySourceProtocol
from app.module.companion.schema.companion_story_schema import (
    CompanionBondSchema,
    CompanionLoreCreateSchema,
    CompanionLoreFragmentSchema,
    CompanionLoreSchema,
    CompanionLoreUpdateSchema,
    CompanionPersonaSchema,
    CompanionPersonaUpdateSchema,
)
from app.module.companion.service.preset_lore_catalog import get_preset
from app.shared.time import utcnow


@dataclass(frozen=True)
class StoryTarget:
    """A resolved companion reference: a shipped preset or an owned custom one."""

    ref: str
    name: str
    preset_id: str | None = None
    companion_id: int | None = None


@dataclass(frozen=True)
class ActiveCompanion:
    """The companion a new conversation speaks as, frozen at creation."""

    ref: str
    name: str
    persona: str
    locale: StoryLocale


def _fragment_from_row(row: CompanionLoreFragmentModel) -> LoreFragment:
    themes = row.themes if isinstance(row.themes, list) else []
    return LoreFragment(
        key=row.fragment_key,
        text=row.text,
        themes=normalize_themes(str(item) for item in themes),
        tier=row.tier,  # type: ignore[arg-type]
        edited=row.edited,
    )


def _bond(model: CompanionBondModel | None) -> Bond:
    if model is None:
        return Bond()
    return Bond(
        completed_runs=model.completed_runs,
        familiar_unlocked_at=model.familiar_unlocked_at,
        rare_unlocked_at=model.rare_unlocked_at,
        last_story_run=model.last_story_run,
    )


class CompanionStoryService:
    """Owner-bound story editing and the persona/lore reads the agent needs."""

    def __init__(
        self,
        *,
        repository: CompanionStoryRepositoryProtocol,
        companions: CompanionLookupProtocol,
        user_id: int,
        config: CompanionStoryConfig = DEFAULT_STORY_CONFIG,
        generated: GeneratedStorySourceProtocol | None = None,
    ) -> None:
        self.repository = repository
        self.companions = companions
        self.user_id = user_id
        self.config = config
        # Published life stories written for this account (``g-<id>`` lore).
        self.generated = generated

    # --- resolution -------------------------------------------------------

    async def resolve(self, companion_ref: str) -> StoryTarget:
        """Resolve a ``preset:<id>`` or ``custom:<id>`` reference or raise 404."""
        selection = parse_selection(companion_ref)
        if selection is None:
            raise CompanionRefNotFoundError(companion_ref)
        if selection.kind == "preset" and selection.preset_id is not None:
            preset = get_preset(selection.preset_id)
            if preset is None:
                raise CompanionRefNotFoundError(companion_ref)
            return StoryTarget(
                ref=selection.serialize(),
                name=preset.name,
                preset_id=preset.preset_id,
            )
        assert selection.companion_id is not None
        companion = await self.companions.get_companion(self.user_id, selection.companion_id)
        if companion is None:
            raise CompanionRefNotFoundError(companion_ref)
        return StoryTarget(
            ref=selection.serialize(),
            name=companion.name,
            companion_id=companion.id,
        )

    async def _story(self, target: StoryTarget, locale: str) -> CompanionStoryModel | None:
        return await self.repository.get_story(
            preset_id=target.preset_id,
            companion_id=target.companion_id,
            locale=locale,
        )

    async def _custom_fallback_stories(
        self,
        target: StoryTarget,
        locale: str,
    ) -> list[CompanionStoryModel]:
        """Return a custom companion's other-locale rows, English first."""
        if target.companion_id is None:
            return []
        rows = await self.repository.list_custom_stories(target.companion_id)
        others = [row for row in rows if row.locale != locale]
        return sorted(others, key=lambda row: (row.locale != "en", row.id))

    def _display_name(self, target: StoryTarget, locale: str) -> str:
        if target.preset_id is not None:
            preset = get_preset(target.preset_id, locale)
            if preset is not None:
                return preset.name
        return target.name

    async def default_persona(self, target: StoryTarget, locale: str) -> str:
        """Return the persona this locale falls back to without an override."""
        if target.preset_id is not None:
            preset = get_preset(target.preset_id, locale)
            assert preset is not None
            return preset.persona
        for row in await self._custom_fallback_stories(target, locale):
            if row.persona:
                return row.persona
        return default_custom_persona(target.name)

    async def default_fragments(
        self,
        target: StoryTarget,
        locale: str,
    ) -> tuple[LoreFragment, ...]:
        """Return the lore this locale falls back to without an account copy."""
        if target.preset_id is not None:
            preset = get_preset(target.preset_id, locale)
            assert preset is not None
            return preset.fragments
        for row in await self._custom_fallback_stories(target, locale):
            if row.lore_customized:
                return tuple(
                    _fragment_from_row(item)
                    for item in await self.repository.list_fragments(row.id)
                )
        return ()

    async def fragments(
        self,
        target: StoryTarget,
        locale: str,
        *,
        include_generated: bool = False,
    ) -> tuple[LoreFragment, ...]:
        """Return the lore in effect for this account and locale.

        ``include_generated`` appends the account's published life stories for
        this companion and locale, so recall and pacing treat them like any
        other lore item. Editing surfaces leave it off.
        """
        story = await self._story(target, locale)
        if story is not None and story.lore_customized:
            items = tuple(
                _fragment_from_row(row) for row in await self.repository.list_fragments(story.id)
            )
        else:
            items = await self.default_fragments(target, locale)
        if not include_generated or self.generated is None:
            return items
        generated = await self.generated.list_published(target.ref, locale)
        return items + tuple(
            LoreFragment(
                key=row.fragment_key,
                text=row.text,
                themes=normalize_themes(str(item) for item in (row.themes or [])),
                tier=row.tier,  # type: ignore[arg-type]
                origin="generated",
            )
            for row in generated
            if not row.fragment_key.startswith("g-pending-")
        )

    async def persona(self, target: StoryTarget, locale: str) -> tuple[str, bool]:
        """Return the persona in effect and whether it is the default."""
        story = await self._story(target, locale)
        if story is not None and story.persona:
            return story.persona, False
        return await self.default_persona(target, locale), True

    # --- agent reads -------------------------------------------------------

    async def active_companion(self, locale: StoryLocale) -> ActiveCompanion | None:
        """Return the enabled, selected companion's persona, or ``None``.

        An account that never chose a companion speaks with the flagship preset.
        A stale custom selection (deleted companion) falls back the same way.
        """
        preference = await self.companions.get_preference(self.user_id)
        if preference is not None and not preference.enabled:
            return None
        selected = preference.selected if preference is not None else None
        default_ref = CompanionSelection(kind="preset", preset_id=DEFAULT_PRESET_ID).serialize()
        target: StoryTarget | None = None
        for ref in (selected, default_ref):
            if not ref:
                continue
            try:
                target = await self.resolve(ref)
            except CompanionRefNotFoundError:
                continue
            break
        if target is None:
            return None
        persona, _default = await self.persona(target, locale)
        return ActiveCompanion(
            ref=target.ref,
            name=self._display_name(target, locale),
            persona=persona,
            locale=locale,
        )

    async def bond(self, companion_ref: str) -> Bond:
        """Return the account's bond with one companion reference."""
        return _bond(await self.repository.get_bond(companion_ref))

    async def told(self, companion_ref: str) -> dict[str, ToldRecord]:
        """Return which fragments of one companion this account has been told."""
        return {
            row.fragment_key: ToldRecord(told_count=row.told_count, last_told_at=row.last_told_at)
            for row in await self.repository.list_told(companion_ref)
        }

    async def record_told(
        self,
        companion_ref: str,
        fragment_keys: Sequence[str],
        source: str,
    ) -> None:
        """Count one offer of each fragment (topical, story_moment, or self_query)."""
        if fragment_keys:
            await self.repository.record_told(companion_ref, list(fragment_keys), source, utcnow())

    async def mark_story_moment(self, companion_ref: str, completed_runs: int) -> None:
        """Remember that a story moment was offered at ``completed_runs``."""
        await self.repository.set_last_story_run(companion_ref, completed_runs, utcnow())

    async def record_completed_run(self, companion_ref: str) -> Bond:
        """Count one completed run and stamp any tier it unlocks."""
        now = utcnow()
        model = await self.repository.increment_bond(companion_ref, now)
        changed = False
        config = self.config
        if (
            model.completed_runs >= config.familiar_unlock_runs
            and model.familiar_unlocked_at is None
        ):
            model.familiar_unlocked_at = now
            changed = True
        if model.completed_runs >= config.rare_unlock_runs and model.rare_unlocked_at is None:
            model.rare_unlocked_at = now
            changed = True
        if changed:
            await self.repository.flush()
        return _bond(model)

    # --- persona editing ---------------------------------------------------

    async def get_persona(self, companion_ref: str, locale: StoryLocale) -> CompanionPersonaSchema:
        target = await self.resolve(companion_ref)
        story = await self._story(target, locale)
        default = await self.default_persona(target, locale)
        override = story.persona if story is not None else None
        return CompanionPersonaSchema(
            companion_ref=target.ref,
            locale=locale,
            name=self._display_name(target, locale),
            persona=override or default,
            is_default=not override,
            default_persona=default,
            updated_at=story.updated_at if story is not None and override else None,
        )

    async def update_persona(
        self,
        companion_ref: str,
        locale: StoryLocale,
        payload: CompanionPersonaUpdateSchema,
    ) -> CompanionPersonaSchema:
        target = await self.resolve(companion_ref)
        story = await self._ensure_story(target, locale)
        story.persona = payload.persona
        story.updated_at = utcnow()
        await self.repository.flush()
        return await self.get_persona(target.ref, locale)

    async def reset_persona(
        self,
        companion_ref: str,
        locale: StoryLocale,
    ) -> CompanionPersonaSchema:
        target = await self.resolve(companion_ref)
        story = await self._story(target, locale)
        if story is not None:
            story.persona = None
            story.updated_at = utcnow()
            await self._drop_if_empty(story)
        return await self.get_persona(target.ref, locale)

    # --- lore editing -------------------------------------------------------

    async def list_lore(self, companion_ref: str, locale: StoryLocale) -> CompanionLoreSchema:
        target = await self.resolve(companion_ref)
        story = await self._story(target, locale)
        customized = story is not None and story.lore_customized
        fragments = await self.fragments(target, locale)
        bond = await self.bond(target.ref)
        unlocked = bond.unlocked_tiers(self.config)
        return CompanionLoreSchema(
            companion_ref=target.ref,
            locale=locale,
            name=self._display_name(target, locale),
            customized=customized,
            bond=CompanionBondSchema(
                completed_runs=bond.completed_runs,
                familiar_unlock_runs=self.config.familiar_unlock_runs,
                rare_unlock_runs=self.config.rare_unlock_runs,
                familiar_unlocked_at=bond.familiar_unlocked_at,
                rare_unlocked_at=bond.rare_unlocked_at,
            ),
            fragments=[
                CompanionLoreFragmentSchema(
                    id=fragment.key,
                    tier=fragment.tier,
                    themes=list(fragment.themes),
                    text=fragment.text,
                    unlocked=fragment.tier in unlocked,
                    unlocked_at=bond.unlocked_at(fragment.tier),
                    edited=fragment.edited,
                    position=index,
                )
                for index, fragment in enumerate(fragments)
            ],
        )

    async def create_lore(
        self,
        companion_ref: str,
        locale: StoryLocale,
        payload: CompanionLoreCreateSchema,
    ) -> CompanionLoreSchema:
        target = await self.resolve(companion_ref)
        story, rows = await self._ensure_lore_copy(target, locale)
        if len(rows) >= MAX_FRAGMENTS_PER_COMPANION:
            raise CompanionLoreLimitError(MAX_FRAGMENTS_PER_COMPANION)
        await self.repository.add_fragment(
            story_id=story.id,
            fragment_key=f"u-{uuid4().hex[:16]}",
            text=payload.text.strip(),
            themes=normalize_themes(payload.themes),
            tier=payload.tier,
            position=(max((row.position for row in rows), default=-1) + 1),
            edited=True,
            now=utcnow(),
        )
        return await self.list_lore(target.ref, locale)

    async def update_lore(
        self,
        companion_ref: str,
        locale: StoryLocale,
        fragment_id: str,
        payload: CompanionLoreUpdateSchema,
    ) -> CompanionLoreSchema:
        target = await self.resolve(companion_ref)
        _story, rows = await self._ensure_lore_copy(target, locale)
        row = next((item for item in rows if item.fragment_key == fragment_id), None)
        if row is None:
            raise CompanionLoreNotFoundError(fragment_id)
        fields = payload.model_fields_set
        if "text" in fields and payload.text is not None:
            row.text = payload.text.strip()
        if "themes" in fields and payload.themes is not None:
            row.themes = list(normalize_themes(payload.themes))
        if "tier" in fields and payload.tier is not None:
            row.tier = payload.tier
        if "position" in fields and payload.position is not None:
            row.position = payload.position
        row.edited = True
        row.updated_at = utcnow()
        await self.repository.flush()
        return await self.list_lore(target.ref, locale)

    async def delete_lore(
        self,
        companion_ref: str,
        locale: StoryLocale,
        fragment_id: str,
    ) -> CompanionLoreSchema:
        target = await self.resolve(companion_ref)
        _story, rows = await self._ensure_lore_copy(target, locale)
        row = next((item for item in rows if item.fragment_key == fragment_id), None)
        if row is None:
            raise CompanionLoreNotFoundError(fragment_id)
        await self.repository.delete_fragment(row)
        return await self.list_lore(target.ref, locale)

    async def reset_lore(self, companion_ref: str, locale: StoryLocale) -> CompanionLoreSchema:
        target = await self.resolve(companion_ref)
        story = await self._story(target, locale)
        if story is not None and story.lore_customized:
            await self.repository.delete_fragments(story.id)
            story.lore_customized = False
            story.updated_at = utcnow()
            await self._drop_if_empty(story)
        return await self.list_lore(target.ref, locale)

    # --- helpers -----------------------------------------------------------

    async def _ensure_story(self, target: StoryTarget, locale: str) -> CompanionStoryModel:
        story = await self._story(target, locale)
        if story is None:
            story = await self.repository.add_story(
                preset_id=target.preset_id,
                companion_id=target.companion_id,
                locale=locale,
                now=utcnow(),
            )
        return story

    async def _ensure_lore_copy(
        self,
        target: StoryTarget,
        locale: str,
    ) -> tuple[CompanionStoryModel, list[CompanionLoreFragmentModel]]:
        """Copy this locale's default lore into owner rows on the first edit."""
        story = await self._ensure_story(target, locale)
        if not story.lore_customized:
            defaults: Sequence[LoreFragment] = await self.default_fragments(target, locale)
            now = utcnow()
            for position, fragment in enumerate(defaults):
                await self.repository.add_fragment(
                    story_id=story.id,
                    fragment_key=fragment.key,
                    text=fragment.text,
                    themes=fragment.themes,
                    tier=fragment.tier,
                    position=position,
                    edited=fragment.edited,
                    now=now,
                )
            story.lore_customized = True
            story.updated_at = now
            await self.repository.flush()
        return story, await self.repository.list_fragments(story.id)

    async def _drop_if_empty(self, story: CompanionStoryModel) -> None:
        if story.persona is None and not story.lore_customized:
            await self.repository.delete_story(story)
        else:
            await self.repository.flush()


__all__ = [
    "ActiveCompanion",
    "CompanionStoryService",
    "LoreTier",
    "StoryTarget",
]
