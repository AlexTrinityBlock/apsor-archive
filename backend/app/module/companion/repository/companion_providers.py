"""Database-backed companion providers: config, content, and account policy.

They implement the companion story protocols over the live, root-editable
tables and keep small in-process caches:

- **Content** (presets, lore, canon, world docs) is cached per
  ``companion_seed_state.content_version``; the version is re-read at most
  every ``ttl`` seconds, and root administration bumps it after every edit.
- **Config** (the global singleton plus templates) and each account's
  overrides and policy are cached for ``ttl`` seconds; :meth:`invalidate`
  drops them at once in the writing process.

Before the first seed (an empty ``companion_seed_state``), every provider
delegates to the injected fallback (the seed-file providers), so a fresh
process never serves an empty world.
"""

import time
from dataclasses import dataclass, field
from typing import Any, cast

from app.infrastructure.database.session import ROLE_USER, Database
from app.module.companion.domain.companion_policy_domain import (
    DEFAULT_ACCOUNT_POLICY,
    AccountCompanionPolicy,
    merge_config_overrides,
)
from app.module.companion.domain.seed_domain import USER_CONFIG_COLUMNS, build_runtime_config
from app.module.companion.domain.story_domain import (
    CanonEntry,
    CompanionRuntimeConfig,
    LoreTier,
    PresetStory,
    StoryItem,
    WorldDoc,
    WorldDocKind,
    normalize_themes,
)
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionStoryConfigProviderProtocol,
)
from app.module.companion.repository.companion_world_repository import (
    CompanionWorldRepository,
    config_values,
)

_DEFAULT_TTL_SECONDS = 10.0


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


@dataclass
class _ContentSnapshot:
    version: int
    preset_rows: list[tuple[str, int, bool, bool]] = field(default_factory=list)
    texts: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    items: dict[str, list[tuple[int, StoryItem]]] = field(default_factory=dict)
    item_texts: dict[tuple[int, str], str] = field(default_factory=dict)
    canon: dict[str, dict[str, CanonEntry]] = field(default_factory=dict)
    docs: dict[tuple[str, str], WorldDoc | None] = field(default_factory=dict)


class DbCompanionContentProvider:
    """Serve presets, lore, canon, and world documents from the live tables."""

    def __init__(
        self,
        database: Database,
        *,
        fallback: CompanionContentProviderProtocol,
        ttl_seconds: float = 5.0,
    ) -> None:
        self.database = database
        self.fallback = fallback
        self.ttl_seconds = ttl_seconds
        self._snapshot: _ContentSnapshot | None = None
        self._checked_at = 0.0

    def invalidate(self) -> None:
        """Re-check the content version on the next read."""
        self._checked_at = 0.0

    async def _current(self) -> _ContentSnapshot | None:
        now = time.monotonic()
        if self._snapshot is not None and now - self._checked_at < self.ttl_seconds:
            return self._snapshot if self._snapshot.version > 0 else None
        async with self.database.public_session() as session:
            repository = CompanionWorldRepository(session)
            version = await repository.content_version()
            if self._snapshot is None or self._snapshot.version != version:
                self._snapshot = await self._load(repository, version)
        self._checked_at = now
        return self._snapshot if self._snapshot.version > 0 else None

    @staticmethod
    async def _load(repository: CompanionWorldRepository, version: int) -> _ContentSnapshot:
        snapshot = _ContentSnapshot(version=version)
        if version <= 0:
            return snapshot
        snapshot.preset_rows = [
            (row.id, row.position, row.enabled, row.is_global_default)
            for row in await repository.list_presets()
        ]
        snapshot.texts = {
            (row.preset_id, row.locale): (row.name, row.persona)
            for row in await repository.list_preset_texts()
        }
        for item in await repository.list_lore_items():
            snapshot.items.setdefault(item.preset_id, []).append(
                (
                    item.id,
                    StoryItem(
                        key=item.fragment_key,
                        text="",
                        themes=normalize_themes(_strings(item.themes)),
                        tier=cast(LoreTier, item.tier),
                        refs=_strings(item.refs),
                        origin="preset",
                    ),
                )
            )
        snapshot.item_texts = {
            (row.item_id, row.locale): row.text for row in await repository.list_lore_item_texts()
        }
        return snapshot

    @staticmethod
    def _story(snapshot: _ContentSnapshot, preset_id: str, locale: str) -> PresetStory | None:
        english = snapshot.texts.get((preset_id, "en"))
        localized = snapshot.texts.get((preset_id, locale)) or english
        if localized is None or english is None:
            return None
        fragments: list[StoryItem] = []
        for item_id, item in snapshot.items.get(preset_id, []):
            text = snapshot.item_texts.get((item_id, locale)) or snapshot.item_texts.get(
                (item_id, "en")
            )
            if text:
                fragments.append(
                    StoryItem(
                        key=item.key,
                        text=text,
                        themes=item.themes,
                        tier=item.tier,
                        refs=item.refs,
                        origin="preset",
                    )
                )
        return PresetStory(
            preset_id=preset_id,
            name=localized[0] or english[0],
            persona=localized[1] or english[1],
            fragments=tuple(fragments),
        )

    async def presets(self, locale: str) -> list[PresetStory]:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.presets(locale)
        stories = [
            self._story(snapshot, preset_id, locale)
            for preset_id, _position, enabled, _default in snapshot.preset_rows
            if enabled
        ]
        return [story for story in stories if story is not None]

    async def preset(self, preset_id: str, locale: str) -> PresetStory | None:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.preset(preset_id, locale)
        return self._story(snapshot, preset_id, locale)

    async def enabled_preset_ids(self) -> list[str]:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.enabled_preset_ids()
        return [row[0] for row in snapshot.preset_rows if row[2]]

    async def global_default_preset_id(self) -> str:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.global_default_preset_id()
        enabled = [row for row in snapshot.preset_rows if row[2]]
        chosen = next((row for row in enabled if row[3]), enabled[0] if enabled else None)
        return chosen[0] if chosen is not None else ""

    async def canon(self, locale: str) -> dict[str, CanonEntry]:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.canon(locale)
        cached = snapshot.canon.get(locale)
        if cached is not None:
            return cached
        async with self.database.public_session() as session:
            rows = await CompanionWorldRepository(session).list_canon(("en", locale))
        english = {
            row.entity_id: CanonEntry(entity_id=row.entity_id, name=row.name, summary=row.summary)
            for row in rows
            if row.locale == "en"
        }
        localized = {
            row.entity_id: CanonEntry(entity_id=row.entity_id, name=row.name, summary=row.summary)
            for row in rows
            if row.locale == locale and locale != "en"
        }
        merged = {**english, **localized}
        snapshot.canon[locale] = merged
        return merged

    async def world_doc(self, doc_key: str, locale: str) -> WorldDoc | None:
        snapshot = await self._current()
        if snapshot is None:
            return await self.fallback.world_doc(doc_key, locale)
        key = (doc_key, locale)
        if key in snapshot.docs:
            return snapshot.docs[key]
        async with self.database.public_session() as session:
            repository = CompanionWorldRepository(session)
            row = await repository.get_world_doc(doc_key, locale)
            if row is None and locale != "en":
                row = await repository.get_world_doc(doc_key, "en")
        doc = (
            WorldDoc(
                doc_key=row.doc_key,
                locale=row.locale,
                kind=cast(WorldDocKind, row.kind),
                title=row.title,
                body_md=row.body_md,
                version=row.version,
            )
            if row is not None
            else None
        )
        snapshot.docs[key] = doc
        return doc

    async def content_version(self) -> int:
        snapshot = await self._current()
        return snapshot.version if snapshot is not None else 0


@dataclass
class _Cached:
    value: Any
    at: float


class DbCompanionConfigProvider:
    """Serve the live story configuration, with root's per-account overrides."""

    def __init__(
        self,
        database: Database,
        *,
        fallback: CompanionStoryConfigProviderProtocol,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self.database = database
        self.fallback = fallback
        self.ttl_seconds = ttl_seconds
        self._global: _Cached | None = None
        self._users: dict[int, _Cached] = {}

    def invalidate(self, user_id: int | None = None) -> None:
        """Drop the cached global config (``None``) or one account's overrides."""
        if user_id is None:
            self._global = None
            self._users.clear()
        else:
            self._users.pop(user_id, None)

    def _fresh(self, cached: _Cached | None) -> bool:
        return cached is not None and time.monotonic() - cached.at < self.ttl_seconds

    async def _global_values(self) -> tuple[dict[str, Any], dict[str, str], int] | None:
        if self._fresh(self._global):
            assert self._global is not None
            return cast(tuple[dict[str, Any], dict[str, str], int] | None, self._global.value)
        async with self.database.public_session() as session:
            repository = CompanionWorldRepository(session)
            seeded = await repository.content_version() > 0
            config = await repository.get_config() if seeded else None
            templates = {
                row.template_key: row.body
                for row in await repository.list_templates()
                if row.locale == "en"
            }
        value = (config_values(config), templates, config.version) if config else None
        self._global = _Cached(value=value, at=time.monotonic())
        return value

    async def _user_overrides(self, user_id: int) -> dict[str, Any]:
        cached = self._users.get(user_id)
        if self._fresh(cached):
            assert cached is not None
            return cast(dict[str, Any], cached.value)
        async with self.database.user_session(user_id, ROLE_USER) as session:
            row = await CompanionWorldRepository(session).get_user_config(user_id)
        overrides = (
            {name: getattr(row, name) for name in USER_CONFIG_COLUMNS} if row is not None else {}
        )
        self._users[user_id] = _Cached(value=overrides, at=time.monotonic())
        return overrides

    async def load(self, user_id: int | None = None) -> CompanionRuntimeConfig:
        """Return the global config, overlaid with ``user_id``'s overrides."""
        global_values = await self._global_values()
        if global_values is None:
            return await self.fallback.load(user_id)
        values, templates, version = global_values
        if user_id is not None:
            overrides = await self._user_overrides(user_id)
            if overrides:
                values = merge_config_overrides(values, overrides)
        return build_runtime_config(values, templates, version=version)


class DbCompanionPolicyProvider:
    """Serve root's companion policy for one account (owner-readable row)."""

    def __init__(self, database: Database, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self.database = database
        self.ttl_seconds = ttl_seconds
        self._cache: dict[int, _Cached] = {}

    def invalidate(self, user_id: int | None = None) -> None:
        """Drop one account's cached policy (or every account's)."""
        if user_id is None:
            self._cache.clear()
        else:
            self._cache.pop(user_id, None)

    async def load(self, user_id: int) -> AccountCompanionPolicy:
        cached = self._cache.get(user_id)
        if cached is not None and time.monotonic() - cached.at < self.ttl_seconds:
            return cast(AccountCompanionPolicy, cached.value)
        async with self.database.user_session(user_id, ROLE_USER) as session:
            row = await CompanionWorldRepository(session).get_account_policy(user_id)
        if row is None:
            policy = DEFAULT_ACCOUNT_POLICY
        else:
            allowed = row.allowed_refs
            policy = AccountCompanionPolicy(
                default_ref=row.default_ref,
                allowed_refs=_strings(allowed) if allowed is not None else None,
                allow_custom=row.allow_custom,
                pinned_ref=row.pinned_ref,
                pin_enabled=row.pin_enabled,
            )
        self._cache[user_id] = _Cached(value=policy, at=time.monotonic())
        return policy


__all__ = [
    "DbCompanionConfigProvider",
    "DbCompanionContentProvider",
    "DbCompanionPolicyProvider",
]
