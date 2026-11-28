"""Companion stories: persona and lore editing, the active persona, and bonds.

Preset stories, the configuration, and root's per-account policy come from
providers over the live, root-editable tables (the seed files are only seed
data). Story layers resolve per item, lowest to highest precedence: the preset
text (locale, then English) < root's per-account override < the account's own
copy-on-write edit; published generated life stories are appended.

An account edits one locale of a preset copy-on-write: the first lore edit
copies that locale's effective lore (preset plus root's layer) into owner
rows, and reset deletes the copy. A custom companion has no shipped default;
its rows are the story, falling back from the requested locale to English and
then to any locale the owner wrote.

The account sees its own lore and the lore it has already heard; tiers, locks,
and progress stay hidden (root sees them in administration).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from app.module.companion.domain.companion_domain import parse_selection
from app.module.companion.domain.companion_policy_domain import (
    AdminLoreOverride,
    StoryLayers,
    resolve_active_companion,
    resolve_persona,
    resolve_story_items,
)
from app.module.companion.domain.story_domain import (
    MAX_FRAGMENTS_PER_COMPANION,
    Bond,
    CompanionRuntimeConfig,
    LoreFragment,
    LoreTier,
    StoryItem,
    StoryLocale,
    ToldRecord,
    custom_persona,
    normalize_themes,
)
from app.module.companion.exception.domain_error import (
    CompanionLoreLimitError,
    CompanionLoreNotFoundError,
    CompanionRefNotFoundError,
)
from app.module.companion.model.companion_admin_model import CompanionAdminLoreOverrideModel
from app.module.companion.model.companion_life_story_model import CompanionGeneratedStoryModel
from app.module.companion.model.companion_story_model import (
    CompanionBondModel,
    CompanionLoreFragmentModel,
    CompanionStoryModel,
)
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionLookupProtocol,
    CompanionPolicyProviderProtocol,
    CompanionStoryConfigProviderProtocol,
    CompanionStoryRepositoryProtocol,
)
from app.module.companion.schema.companion_story_schema import (
    CompanionLoreCreateSchema,
    CompanionLoreFragmentSchema,
    CompanionLoreSchema,
    CompanionLoreUpdateSchema,
    CompanionPersonaSchema,
    CompanionPersonaUpdateSchema,
)
from app.shared.time import utcnow


@dataclass(frozen=True)
class StoryTarget:
    """A resolved companion reference: a preset or an owned custom one."""

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


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _fragment_from_row(row: CompanionLoreFragmentModel) -> LoreFragment:
    return LoreFragment(
        key=row.fragment_key,
        text=row.text,
        themes=normalize_themes(_strings(row.themes)),
        tier=cast(LoreTier, row.tier),
        edited=row.edited,
        refs=tuple(_strings(getattr(row, "refs", None))),
        origin="user",
    )


def _admin_override(row: CompanionAdminLoreOverrideModel) -> AdminLoreOverride:
    item = None
    if row.action != "hide" and row.text:
        item = StoryItem(
            key=row.fragment_key,
            text=row.text,
            themes=normalize_themes(_strings(row.themes)),
            tier=cast(LoreTier, row.tier or "first"),
            refs=tuple(_strings(row.refs)),
            origin="admin",
        )
    return AdminLoreOverride(
        key=row.fragment_key,
        action=cast(Any, row.action),
        item=item,
        position=row.position,
    )


def _generated_item(row: CompanionGeneratedStoryModel) -> StoryItem:
    return StoryItem(
        key=row.fragment_key,
        text=row.text,
        themes=normalize_themes(_strings(row.themes)),
        tier=cast(LoreTier, row.tier),
        origin="generated",
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
        content: CompanionContentProviderProtocol,
        config: CompanionStoryConfigProviderProtocol,
        policy: CompanionPolicyProviderProtocol,
    ) -> None:
        self.repository = repository
        self.companions = companions
        self.user_id = user_id
        self.content = content
        self.config_provider = config
        self.policy = policy

    async def config(self) -> CompanionRuntimeConfig:
        """Return the live configuration for this account (root's overrides applied)."""
        return await self.config_provider.load(self.user_id)

    # --- resolution -------------------------------------------------------

    async def resolve(self, companion_ref: str) -> StoryTarget:
        """Resolve a ``preset:<id>`` or ``custom:<id>`` reference or raise 404."""
        selection = parse_selection(companion_ref)
        if selection is None:
            raise CompanionRefNotFoundError(companion_ref)
        if selection.kind == "preset" and selection.preset_id is not None:
            preset = await self.content.preset(selection.preset_id, "en")
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

    async def preset_names(self, locale: str) -> list[str]:
        """Return every enabled preset's name in English and ``locale``."""
        names: set[str] = set()
        for each in {"en", locale}:
            names.update(preset.name for preset in await self.content.presets(each))
        return sorted(name for name in names if name)

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

    async def _display_name(self, target: StoryTarget, locale: str) -> str:
        if target.preset_id is not None:
            preset = await self.content.preset(target.preset_id, locale)
            if preset is not None:
                return preset.name
        return target.name

    async def default_persona(self, target: StoryTarget, locale: str) -> str:
        """Return the persona this locale falls back to without the account's edit."""
        admin = await self.repository.get_admin_persona(target.ref, locale)
        if target.preset_id is not None:
            preset = await self.content.preset(target.preset_id, locale)
            english = await self.content.preset(target.preset_id, "en")
            return resolve_persona(
                user_persona=None,
                admin_persona=admin,
                preset_persona=preset.persona if preset is not None else None,
                english_preset_persona=english.persona if english is not None else None,
                fallback=custom_persona(await self.config(), target.name),
            )
        if admin:
            return admin
        for row in await self._custom_fallback_stories(target, locale):
            if row.persona:
                return row.persona
        return custom_persona(await self.config(), target.name)

    async def default_fragments(
        self,
        target: StoryTarget,
        locale: str,
    ) -> tuple[LoreFragment, ...]:
        """Return the lore this locale falls back to without an account copy.

        For a preset this is the preset lore with root's per-account layer
        applied; for a custom companion, the owner's other-locale rows.
        """
        if target.preset_id is not None:
            preset = await self.content.preset(target.preset_id, locale)
            items = preset.fragments if preset is not None else ()
            overrides = tuple(
                _admin_override(row)
                for row in await self.repository.list_admin_lore_overrides(target.ref, locale)
            )
            return resolve_story_items(StoryLayers(preset_items=items, admin_overrides=overrides))
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
        user_items: tuple[StoryItem, ...] | None = None
        if story is not None and story.lore_customized:
            user_items = tuple(
                _fragment_from_row(row) for row in await self.repository.list_fragments(story.id)
            )
        base = user_items if user_items is not None else await self.default_fragments(
            target, locale
        )
        generated: tuple[StoryItem, ...] = ()
        if include_generated:
            generated = tuple(
                _generated_item(row)
                for row in await self.repository.list_published_generated(target.ref)
                if row.locale == locale and not row.fragment_key.startswith("g-pending-")
            )
        return resolve_story_items(StoryLayers(user_items=base, generated_items=generated))

    async def persona(self, target: StoryTarget, locale: str) -> tuple[str, bool]:
        """Return the persona in effect and whether it is the default."""
        story = await self._story(target, locale)
        if story is not None and story.persona:
            return story.persona, False
        return await self.default_persona(target, locale), True

    # --- agent reads -------------------------------------------------------

    async def active_companion(self, locale: StoryLocale) -> ActiveCompanion | None:
        """Return the enabled, active companion's persona, or ``None``.

        The active companion resolves as root's pin > the account's own choice
        (when allowed) > root's default for the account > the global default
        preset. A stale selection (deleted companion) falls through the same way.
        """
        preference = await self.companions.get_preference(self.user_id)
        if preference is not None and not preference.enabled:
            return None
        policy = await self.policy.load(self.user_id)
        enabled = await self.content.enabled_preset_ids()
        global_default = await self.content.global_default_preset_id()
        customs = [
            f"custom:{companion.id}"
            for companion in await self.companions.list_companions(self.user_id)
        ]
        choice = resolve_active_companion(
            user_selected=preference.selected if preference is not None else None,
            policy=policy,
            global_default=f"preset:{global_default}",
            enabled_presets=enabled,
            custom_refs=customs,
        )
        try:
            target = await self.resolve(choice.ref)
        except CompanionRefNotFoundError:
            return None
        persona, _default = await self.persona(target, locale)
        return ActiveCompanion(
            ref=target.ref,
            name=await self._display_name(target, locale),
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
        config = await self.config()
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
            name=await self._display_name(target, locale),
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
        """Return what the account may see: its own lore and the lore it has heard.

        Tiers, locks, and progress are never shown to the account.
        """
        target = await self.resolve(companion_ref)
        story = await self._story(target, locale)
        customized = story is not None and story.lore_customized
        fragments = await self.fragments(target, locale)
        told = await self.told(target.ref)
        visible: list[CompanionLoreFragmentSchema] = []
        for index, fragment in enumerate(fragments):
            own = fragment.key.startswith("u-") or (
                target.companion_id is not None and fragment.origin == "user"
            )
            heard = told.get(fragment.key, ToldRecord()).told_count > 0
            if not (own or heard or fragment.edited):
                continue
            visible.append(
                CompanionLoreFragmentSchema(
                    id=fragment.key,
                    themes=list(fragment.themes),
                    text=fragment.text,
                    edited=fragment.edited,
                    own=own,
                    heard=heard,
                    position=index,
                )
            )
        return CompanionLoreSchema(
            companion_ref=target.ref,
            locale=locale,
            name=await self._display_name(target, locale),
            customized=customized,
            fragments=visible,
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
        """Copy this locale's effective default lore into owner rows on the first edit."""
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
