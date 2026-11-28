"""Seed-backed providers for companion configuration, content, and policy.

Every tunable of companion stories, the preset stories, the canon, and the
world documents are root-editable and live in the database. Until (and in
tests where) the database-backed providers are not installed, these static
providers serve the shipped seed data behind the same protocols:

- :class:`StaticStoryConfigProvider` — the seed :class:`CompanionRuntimeConfig`
  (global and per account alike).
- :class:`StaticCompanionContentProvider` — presets, canon, and world documents
  read from ``companion/lore``.
- :class:`StaticCompanionPolicyProvider` — the unrestricted default policy.
"""

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from app.module.companion.domain.companion_policy_domain import (
    DEFAULT_ACCOUNT_POLICY,
    AccountCompanionPolicy,
)
from app.module.companion.domain.story_domain import (
    DEFAULT_PRESET_ID,
    DEFAULT_RUNTIME_CONFIG,
    CanonEntry,
    CompanionRuntimeConfig,
    CompanionStoryConfig,
    PresetStory,
    WorldDoc,
    WorldDocKind,
)
from app.module.companion.service.preset_lore_catalog import LORE_DIRECTORY, load_presets


def as_runtime_config(config: CompanionStoryConfig) -> CompanionRuntimeConfig:
    """Lift a plain story config into a runtime config with seed templates."""
    if isinstance(config, CompanionRuntimeConfig):
        return config
    values = {field.name: getattr(config, field.name) for field in fields(CompanionStoryConfig)}
    return CompanionRuntimeConfig(**values, templates=DEFAULT_RUNTIME_CONFIG.templates)


class StaticStoryConfigProvider:
    """Serve one fixed configuration (the seed defaults unless given one)."""

    def __init__(self, config: CompanionStoryConfig = DEFAULT_RUNTIME_CONFIG) -> None:
        self.config = as_runtime_config(config)

    async def load(self, user_id: int | None = None) -> CompanionRuntimeConfig:
        """Return the configuration (identical for every account)."""
        return self.config


def _doc_kind(doc_key: str) -> WorldDocKind | None:
    if doc_key.startswith("character:"):
        return "character"
    if doc_key in {"bible", "glossary", "world", "terms"}:
        return doc_key  # type: ignore[return-value]
    return None


class StaticCompanionContentProvider:
    """Serve preset stories, canon, and world documents from the seed files."""

    def __init__(self, directory: Path = LORE_DIRECTORY) -> None:
        self.directory = directory

    async def presets(self, locale: str) -> list[PresetStory]:
        """Return every shipped preset in ``locale`` (English fallback per item)."""
        loaded = load_presets(locale, self.directory)
        return list(loaded.values())

    async def preset(self, preset_id: str, locale: str) -> PresetStory | None:
        """Return one shipped preset in ``locale``."""
        return load_presets(locale, self.directory).get(preset_id)

    async def enabled_preset_ids(self) -> list[str]:
        """Return every shipped preset id, flagship first."""
        ids = sorted(load_presets("en", self.directory))
        return sorted(ids, key=lambda preset_id: preset_id != DEFAULT_PRESET_ID)

    async def global_default_preset_id(self) -> str:
        """Return the flagship preset id."""
        return DEFAULT_PRESET_ID

    async def canon(self, locale: str) -> dict[str, CanonEntry]:
        """Return canon entities in ``locale`` with English fallback per entity."""
        english = self._read_canon(self.directory / "canon.json")
        if locale == "en":
            return english
        localized = self._read_canon(self.directory / locale / "canon.json")
        return {**english, **localized}

    async def world_doc(self, doc_key: str, locale: str) -> WorldDoc | None:
        """Return one world document from the seed files, or ``None``."""
        kind = _doc_kind(doc_key)
        if kind is None:
            return None
        path = self._doc_path(doc_key, locale) or self._doc_path(doc_key, "en")
        if path is None:
            return None
        body = path.read_text(encoding="utf-8")
        title = next(
            (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("#")),
            doc_key,
        )
        return WorldDoc(
            doc_key=doc_key,
            locale=locale,
            kind=kind,
            title=title[:160],
            body_md=body,
        )

    async def content_version(self) -> int:
        """Return a constant version: seed files do not change at runtime."""
        return 0

    def _doc_path(self, doc_key: str, locale: str) -> Path | None:
        base = self.directory if locale == "en" else self.directory / locale
        names = {
            "bible": "BIBLE.md",
            "glossary": "GLOSSARY.md",
            "world": "world.md",
            "terms": "TERMS.md",
        }
        if doc_key.startswith("character:"):
            candidate = base / "characters" / f"{doc_key.split(':', 1)[1]}.md"
        else:
            candidate = base / names[doc_key]
        return candidate if candidate.is_file() else None

    @staticmethod
    def _read_canon(path: Path) -> dict[str, CanonEntry]:
        if not path.is_file():
            return {}
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        entities = raw.get("entities", raw) if isinstance(raw, dict) else raw
        result: dict[str, CanonEntry] = {}
        if isinstance(entities, dict):
            items = list(entities.items())
        else:
            items = [(entry.get("id"), entry) for entry in entities if isinstance(entry, dict)]
        for entity_id, entry in items:
            if not isinstance(entity_id, str):
                continue
            if isinstance(entry, dict):
                name = str(entry.get("name") or entity_id)
                summary = str(entry.get("summary") or entry.get("definition") or "")
            else:
                name, summary = entity_id, str(entry)
            result[entity_id] = CanonEntry(entity_id=entity_id, name=name, summary=summary)
        return result


class StaticCompanionPolicyProvider:
    """Serve the unrestricted default policy for every account."""

    def __init__(self, policy: AccountCompanionPolicy = DEFAULT_ACCOUNT_POLICY) -> None:
        self.policy = policy

    async def load(self, user_id: int) -> AccountCompanionPolicy:
        """Return the policy (identical for every account)."""
        return self.policy


__all__ = [
    "StaticCompanionContentProvider",
    "StaticCompanionPolicyProvider",
    "StaticStoryConfigProvider",
    "as_runtime_config",
]
