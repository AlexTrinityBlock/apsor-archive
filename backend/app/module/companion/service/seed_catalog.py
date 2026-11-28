"""Parse the shipped companion seed bundle into database rows (pure, validated).

The files under ``companion/lore`` are the **seed**, never the live data:

- ``<id>.json`` (English, canonical) and ``<locale>/<id>.json`` translations:
  presets, personas, and lore fragments.
- ``canon.json`` and ``<locale>/canon.json``: canon entities.
- ``BIBLE.md``, ``GLOSSARY.md``, ``world.md``, ``characters/<id>.md`` and the
  locale folders' ``world.md`` / ``TERMS.md``: world documents.
- ``seed/config.json``: every story tunable, word list, preset order, and the
  global default preset.
- ``seed/templates/<key>.<locale>.md``: guidance strings and prompt templates.

:func:`load_seed_bundle` turns them into per-table row dictionaries, each with a
``seed_hash`` of its shipped content, plus one ``content_hash`` for the whole
bundle. The seeder writes the rows; the providers read the database. Nothing
reads these files at request time once the database is seeded, except the
static fallback providers used before seeding (and in unit tests).
"""

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.module.companion.domain.seed_domain import (
    LIFE_STORY_FIELDS,
    SEED_BUNDLE,
    TUNABLE_FIELDS,
    WORD_LIST_FIELDS,
    build_runtime_config,
)
from app.module.companion.domain.story_domain import (
    LORE_WEIGHTS,
    STORY_LOCALES,
    TEMPLATE_KEYS,
    CompanionRuntimeConfig,
    missing_placeholders,
)
from app.module.companion.service.preset_lore_catalog import (
    LORE_DIRECTORY,
    PresetLoreError,
    load_presets,
)

# Bump when the row layout (not the content) changes, to force a reseed.
SEED_SCHEMA_VERSION = 1
SEED_DIRECTORY = LORE_DIRECTORY / "seed"

_WORLD_DOC_FILES: dict[str, str] = {
    "bible": "BIBLE.md",
    "glossary": "GLOSSARY.md",
    "world": "world.md",
    "terms": "TERMS.md",
}

# Bounds mirror the companion_config CHECK constraints.
_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "max_recalled_fragments": (0, 5),
    "told_penalty_cap": (0, 20),
    "story_moment_every_runs": (0, 100),
    "self_query_window": (1, 50),
    "max_contributions_per_run": (0, 5),
    "life_story_every_conversations": (3, 1000),
    "life_story_max_per_30d": (0, 60),
    "life_story_memory_limit": (1, 40),
    "life_story_memory_chars": (500, 20000),
    "life_story_canon_chars": (500, 20000),
    "life_story_max_output_tokens": (200, 8000),
    "life_story_max_chars": (400, 4000),
    "life_story_poll_seconds": (5, 3600),
    "life_story_max_attempts": (1, 10),
}
_FLOAT_FIELDS = frozenset({"topical_min_similarity", "untold_bonus", "told_penalty"})


class SeedBundleError(PresetLoreError):
    """A shipped seed file is malformed (a deployment bug)."""


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedBundleError(f"{path.name}: unreadable seed file") from exc


def _title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:160] or fallback
    return fallback


def _entity_name(entity_id: str) -> str:
    return entity_id.replace("-", " ").title()[:120]


@dataclass(frozen=True)
class SeedBundle:
    """Every seed row, keyed by table, plus a hash of the whole bundle.

    ``rows[table]`` is a list of column dictionaries. Lore item text rows carry
    ``preset_id`` and ``fragment_key`` instead of the database ``item_id``; the
    seeder resolves them.
    """

    rows: dict[str, list[dict[str, Any]]]
    content_hash: str
    preset_order: tuple[str, ...]
    global_default: str
    templates: dict[tuple[str, str], str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


def _validate_config(raw: Any) -> tuple[dict[str, Any], tuple[str, ...], str]:
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise SeedBundleError("seed/config.json: expected an object with schema 1")
    presets = raw.get("presets") or {}
    order = presets.get("order")
    default = presets.get("global_default")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise SeedBundleError("seed/config.json: presets.order must be a list of ids")
    if not isinstance(default, str) or default not in order:
        raise SeedBundleError("seed/config.json: presets.global_default must be in order")
    tunables = raw.get("tunables") or {}
    life_story = raw.get("life_story") or {}
    values: dict[str, Any] = {}
    for name in TUNABLE_FIELDS:
        if name not in tunables:
            raise SeedBundleError(f"seed/config.json: missing tunables.{name}")
        values[name] = tunables[name]
    for name in LIFE_STORY_FIELDS:
        if name not in life_story:
            raise SeedBundleError(f"seed/config.json: missing life_story.{name}")
        values[f"life_story_{name}"] = life_story[name]
    for name in WORD_LIST_FIELDS:
        words = raw.get(name)
        if not isinstance(words, list) or not all(isinstance(item, str) for item in words):
            raise SeedBundleError(f"seed/config.json: {name} must be a list of strings")
        values[name] = [item.strip() for item in words if item.strip()]
    for name, (low, high) in _INT_BOUNDS.items():
        value = values[name]
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise SeedBundleError(f"seed/config.json: {name} must be an int in [{low}, {high}]")
    for name in _FLOAT_FIELDS:
        value = values[name]
        if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= value <= 1:
            raise SeedBundleError(f"seed/config.json: {name} must be a number in [0, 1]")
        values[name] = float(value)
    if values["life_story_weight"] not in LORE_WEIGHTS:
        raise SeedBundleError("seed/config.json: life_story.weight must be a lore weight")
    for name in ("life_story_enabled", "life_story_require_review"):
        if not isinstance(values[name], bool):
            raise SeedBundleError(f"seed/config.json: {name} must be a boolean")
    return values, tuple(order), default


def _templates(directory: Path) -> dict[tuple[str, str], str]:
    templates: dict[tuple[str, str], str] = {}
    for path in sorted(directory.glob("*.md")):
        key, _, rest = path.name.partition(".")
        locale = rest.removesuffix(".md")
        if key not in TEMPLATE_KEYS:
            raise SeedBundleError(f"seed/templates/{path.name}: unknown template key")
        if locale not in STORY_LOCALES:
            raise SeedBundleError(f"seed/templates/{path.name}: unknown locale")
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            raise SeedBundleError(f"seed/templates/{path.name}: empty template")
        missing = missing_placeholders(key, body)
        if missing:
            raise SeedBundleError(f"seed/templates/{path.name}: lost placeholders {missing}")
        templates[(key, locale)] = body
    for key in TEMPLATE_KEYS:
        if (key, "en") not in templates:
            raise SeedBundleError(f"seed/templates: missing {key}.en.md")
    return templates


def _canon_rows(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for locale in STORY_LOCALES:
        path = directory / "canon.json" if locale == "en" else directory / locale / "canon.json"
        if not path.is_file():
            continue
        raw = _read_json(path)
        entities = raw.get("entities") if isinstance(raw, dict) else None
        if not isinstance(entities, dict):
            raise SeedBundleError(f"{locale}/canon.json: expected an entities object")
        for entity_id, value in entities.items():
            if isinstance(value, dict):
                name = str(value.get("name") or _entity_name(entity_id))
                summary = str(value.get("summary") or value.get("definition") or "")
            else:
                name, summary = _entity_name(entity_id), str(value)
            rows.append(
                {
                    "entity_id": entity_id[:64],
                    "locale": locale,
                    "name": name[:120],
                    "summary": summary.strip(),
                }
            )
    return rows


def _world_doc_rows(directory: Path, preset_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for locale in STORY_LOCALES:
        base = directory if locale == "en" else directory / locale
        candidates: list[tuple[str, str, Path]] = [
            (doc_key, doc_key, base / file_name) for doc_key, file_name in _WORLD_DOC_FILES.items()
        ]
        candidates += [
            (f"character:{preset_id}", "character", base / "characters" / f"{preset_id}.md")
            for preset_id in preset_ids
        ]
        for doc_key, kind, path in candidates:
            if not path.is_file():
                continue
            body = path.read_text(encoding="utf-8").strip()
            rows.append(
                {
                    "doc_key": doc_key,
                    "locale": locale,
                    "kind": kind,
                    "title": _title(body, doc_key),
                    "body_md": body,
                }
            )
    return rows


def _translation(directory: Path, locale: str, preset_id: str) -> dict[str, Any]:
    path = directory / locale / f"{preset_id}.json"
    if not path.is_file():
        return {}
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise SeedBundleError(f"{locale}/{preset_id}.json: expected an object")
    return cast(dict[str, Any], raw)


def _preset_rows(
    directory: Path,
    order: tuple[str, ...],
    global_default: str,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    english = load_presets("en", directory)
    missing = [preset_id for preset_id in order if preset_id not in english]
    if missing:
        raise SeedBundleError(f"seed/config.json: presets without lore files {missing}")
    ids = [*order, *sorted(set(english) - set(order))]
    presets: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    item_texts: list[dict[str, Any]] = []
    for position, preset_id in enumerate(ids):
        preset = english[preset_id]
        presets.append(
            {
                "id": preset_id,
                "position": position,
                "enabled": True,
                "is_global_default": preset_id == global_default,
            }
        )
        texts.append(
            {"preset_id": preset_id, "locale": "en", "name": preset.name, "persona": preset.persona}
        )
        for index, fragment in enumerate(preset.fragments):
            items.append(
                {
                    "preset_id": preset_id,
                    "fragment_key": fragment.key,
                    "weight": fragment.weight,
                    "themes": list(fragment.themes),
                    "refs": list(fragment.refs),
                    "position": index,
                }
            )
            item_texts.append(
                {
                    "preset_id": preset_id,
                    "fragment_key": fragment.key,
                    "locale": "en",
                    "text": fragment.text,
                }
            )
        keys = {fragment.key for fragment in preset.fragments}
        for locale in STORY_LOCALES:
            if locale == "en":
                continue
            raw = _translation(directory, locale, preset_id)
            if not raw:
                continue
            name = raw.get("name")
            persona = raw.get("persona")
            named = isinstance(name, str) and bool(name.strip())
            if named and isinstance(persona, str) and persona.strip():
                assert isinstance(name, str)
                texts.append(
                    {
                        "preset_id": preset_id,
                        "locale": locale,
                        "name": name.strip()[:40],
                        "persona": persona.strip(),
                    }
                )
            for item in raw.get("fragments") or []:
                if not isinstance(item, dict):
                    continue
                key = item.get("id")
                text = item.get("text")
                if isinstance(key, str) and key in keys and isinstance(text, str) and text.strip():
                    item_texts.append(
                        {
                            "preset_id": preset_id,
                            "fragment_key": key,
                            "locale": locale,
                            "text": text.strip(),
                        }
                    )
    rows = {
        "companion_preset": presets,
        "companion_preset_text": texts,
        "companion_lore_item": items,
        "companion_lore_item_text": item_texts,
    }
    return rows, ids


def _with_hashes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "seed_hash": _hash(row)} for row in rows]


@lru_cache(maxsize=2)
def load_seed_bundle(directory: Path = LORE_DIRECTORY) -> SeedBundle:
    """Parse and validate the whole seed bundle (cached per process)."""
    seed_dir = directory / "seed"
    config_values, order, global_default = _validate_config(_read_json(seed_dir / "config.json"))
    templates = _templates(seed_dir / "templates")
    preset_rows, preset_ids = _preset_rows(directory, order, global_default)
    rows: dict[str, list[dict[str, Any]]] = {
        **preset_rows,
        "companion_canon_entity": _canon_rows(directory),
        "companion_world_doc": _world_doc_rows(directory, preset_ids),
        "companion_prompt_template": [
            {
                "template_key": key,
                "locale": locale,
                "body": body,
                "required_placeholders": [],
            }
            for (key, locale), body in sorted(templates.items())
        ],
        "companion_config": [{"id": 1, **config_values}],
    }
    hashed = {table: _with_hashes(table_rows) for table, table_rows in rows.items()}
    content_hash = _hash({"schema": SEED_SCHEMA_VERSION, "rows": rows})
    return SeedBundle(
        rows=hashed,
        content_hash=content_hash,
        preset_order=tuple(preset_ids),
        global_default=global_default,
        templates=templates,
        config=config_values,
    )


@lru_cache(maxsize=1)
def seed_runtime_config() -> CompanionRuntimeConfig:
    """Return the shipped (seed) configuration with its English templates."""
    bundle = load_seed_bundle()
    english = {key: body for (key, locale), body in bundle.templates.items() if locale == "en"}
    return build_runtime_config(bundle.config, english)


__all__ = [
    "LIFE_STORY_FIELDS",
    "SEED_BUNDLE",
    "SEED_DIRECTORY",
    "SEED_SCHEMA_VERSION",
    "TUNABLE_FIELDS",
    "WORD_LIST_FIELDS",
    "SeedBundle",
    "SeedBundleError",
    "load_seed_bundle",
    "seed_runtime_config",
]
