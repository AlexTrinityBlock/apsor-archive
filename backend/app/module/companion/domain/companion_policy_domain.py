"""Pure rules for which companion is active and which story layers apply.

Two parties choose separately and never overwrite each other:

- **Root** sets an account policy: a default companion, an optional allowed
  set, whether custom companions are allowed, and an optional pin (off by
  default).
- **The account** keeps its own choice, visibility, size, opacity, and motion.

The active companion is resolved as: pinned (when the pin is enabled) >
the account's own choice (when allowed) > root's default for the account
(when allowed) > the global default preset. The account's own choice is never
erased: if root narrows and later widens the allowed set, it comes back.

Story layers resolve per item, lowest to highest precedence:
preset text (locale, then English) < root's per-account override < the
account's own copy-on-write edit. Generated life stories are appended.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.module.companion.domain.story_domain import StoryItem

ChoiceSource = Literal["pinned", "user", "admin_default", "global_default"]
LoreOverrideAction = Literal["replace", "add", "hide"]


@dataclass(frozen=True)
class AccountCompanionPolicy:
    """Root's companion policy for one account (defaults: no restriction)."""

    default_ref: str | None = None
    # ``None`` allows every enabled preset plus the account's custom companions.
    allowed_refs: tuple[str, ...] | None = None
    allow_custom: bool = True
    pinned_ref: str | None = None
    pin_enabled: bool = False


DEFAULT_ACCOUNT_POLICY = AccountCompanionPolicy()


@dataclass(frozen=True)
class CompanionChoice:
    """The resolved active companion and why it won."""

    ref: str
    source: ChoiceSource

    @property
    def pinned(self) -> bool:
        """Return whether root's pin decided the choice."""
        return self.source == "pinned"


@dataclass(frozen=True)
class AdminLoreOverride:
    """Root's per-account change to one lore item (replace, add, or hide)."""

    key: str
    action: LoreOverrideAction
    item: StoryItem | None = None
    position: int | None = None


@dataclass(frozen=True)
class StoryLayers:
    """Every layer that may contribute to one account's story for one companion."""

    preset_items: tuple[StoryItem, ...] = ()
    admin_overrides: tuple[AdminLoreOverride, ...] = ()
    # The account's copy-on-write set replaces the admin-applied set when present.
    user_items: tuple[StoryItem, ...] | None = None
    generated_items: tuple[StoryItem, ...] = field(default_factory=tuple)


def allowed_refs(
    policy: AccountCompanionPolicy,
    *,
    enabled_presets: Sequence[str],
    custom_refs: Sequence[str],
) -> tuple[str, ...]:
    """Return the refs this account may choose, in a stable order."""
    preset_refs = [f"preset:{preset_id}" for preset_id in enabled_presets]
    customs = list(custom_refs) if policy.allow_custom else []
    available = [*preset_refs, *customs]
    if policy.allowed_refs is None:
        return tuple(available)
    wanted = set(policy.allowed_refs)
    # Custom companions stay selectable unless custom companions are disallowed.
    return tuple(ref for ref in available if ref in wanted or ref in customs)


def is_allowed(
    ref: str | None,
    policy: AccountCompanionPolicy,
    *,
    enabled_presets: Sequence[str],
    custom_refs: Sequence[str],
) -> bool:
    """Return whether ``ref`` is currently selectable for the account."""
    if not ref:
        return False
    return ref in allowed_refs(policy, enabled_presets=enabled_presets, custom_refs=custom_refs)


def resolve_active_companion(
    *,
    user_selected: str | None,
    policy: AccountCompanionPolicy,
    global_default: str,
    enabled_presets: Sequence[str],
    custom_refs: Sequence[str],
) -> CompanionChoice:
    """Resolve the active companion: pin > user choice > admin default > global."""
    options = allowed_refs(policy, enabled_presets=enabled_presets, custom_refs=custom_refs)
    known = {f"preset:{preset_id}" for preset_id in enabled_presets} | set(custom_refs)
    if policy.pin_enabled and policy.pinned_ref and policy.pinned_ref in known:
        return CompanionChoice(ref=policy.pinned_ref, source="pinned")
    if user_selected and user_selected in options:
        return CompanionChoice(ref=user_selected, source="user")
    if policy.default_ref and policy.default_ref in options:
        return CompanionChoice(ref=policy.default_ref, source="admin_default")
    if global_default in options or not options:
        return CompanionChoice(ref=global_default, source="global_default")
    return CompanionChoice(ref=options[0], source="global_default")


def resolve_persona(
    *,
    user_persona: str | None,
    admin_persona: str | None,
    preset_persona: str | None,
    english_preset_persona: str | None,
    fallback: str,
) -> str:
    """Return the persona: user edit > admin override > preset (locale, English)."""
    for candidate in (user_persona, admin_persona, preset_persona, english_preset_persona):
        if candidate and candidate.strip():
            return candidate
    return fallback


def _position(override: AdminLoreOverride, end: int) -> int:
    """Return the insertion index of an added item (the end when unset)."""
    return end if override.position is None else max(0, override.position)


def apply_admin_overrides(
    items: Iterable[StoryItem],
    overrides: Iterable[AdminLoreOverride],
) -> tuple[StoryItem, ...]:
    """Apply root's replace / add / hide overrides to the preset items."""
    result: list[StoryItem] = list(items)
    index = {item.key: position for position, item in enumerate(result)}
    hidden: set[str] = set()
    additions: list[tuple[int, StoryItem]] = []
    for override in overrides:
        if override.action == "hide":
            hidden.add(override.key)
        elif override.action == "replace" and override.item is not None:
            if override.key in index:
                result[index[override.key]] = override.item
            else:
                additions.append((_position(override, len(result)), override.item))
        elif override.action == "add" and override.item is not None:
            additions.append((_position(override, len(result)), override.item))
    for position, item in sorted(additions, key=lambda pair: pair[0]):
        result.insert(min(position, len(result)), item)
    return tuple(item for item in result if item.key not in hidden)


def resolve_story_items(layers: StoryLayers) -> tuple[StoryItem, ...]:
    """Return the account's effective lore for one companion and locale."""
    base = (
        layers.user_items
        if layers.user_items is not None
        else apply_admin_overrides(layers.preset_items, layers.admin_overrides)
    )
    seen = {item.key for item in base}
    generated = tuple(item for item in layers.generated_items if item.key not in seen)
    return (*base, *generated)


def merge_config_overrides(
    base: Mapping[str, object],
    overrides: Mapping[str, object | None],
) -> dict[str, object]:
    """Overlay non-NULL per-account values on the global tunables."""
    merged = dict(base)
    for key, value in overrides.items():
        if value is not None and key in merged:
            merged[key] = value
    return merged


__all__ = [
    "DEFAULT_ACCOUNT_POLICY",
    "AccountCompanionPolicy",
    "AdminLoreOverride",
    "ChoiceSource",
    "CompanionChoice",
    "LoreOverrideAction",
    "StoryLayers",
    "allowed_refs",
    "apply_admin_overrides",
    "is_allowed",
    "merge_config_overrides",
    "resolve_active_companion",
    "resolve_persona",
    "resolve_story_items",
]
