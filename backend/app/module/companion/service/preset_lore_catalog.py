"""Load the shipped preset stories from ``app/module/companion/lore``.

English is canonical: each preset is ``lore/<id>.json`` (``schema`` 1) and owns
the fragment ids, weights, and themes. Optional translations live in
``lore/zh-TW/<id>.json`` and ``lore/zh-CN/<id>.json`` with the same ids; a
translation may override ``name``, ``persona``, and each fragment's ``text``.
Anything missing falls back to English per item, so told progress stays
locale-independent. ``canon.json`` names the shared world entities that a
fragment's ``refs`` may point at. Themes are editor metadata only: recall is
semantic and never gated by keywords.

The files are read once per process and validated strictly; a malformed shipped
file is a deployment bug, so it raises.
"""

import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.module.companion.domain.story_domain import (
    FRAGMENT_MAX_CHARS,
    LEGACY_TIER_WEIGHTS,
    LORE_WEIGHTS,
    PERSONA_MAX_CHARS,
    STORY_LOCALES,
    LoreFragment,
    LoreWeight,
    PresetStory,
    is_fragment_key,
    normalize_themes,
)

LORE_DIRECTORY = Path(__file__).resolve().parent.parent / "lore"
_RESERVED_FILES = frozenset({"canon.json"})


class PresetLoreError(RuntimeError):
    """A shipped lore file is malformed."""


def _canon_entities(directory: Path) -> frozenset[str] | None:
    path = directory / "canon.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    entities = raw.get("entities") if isinstance(raw, dict) else None
    if not isinstance(entities, dict) or not all(isinstance(key, str) for key in entities):
        raise PresetLoreError("canon.json: expected an entities object")
    return frozenset(entities)


def _fragment(raw: Any, source: str) -> LoreFragment:
    if not isinstance(raw, dict):
        raise PresetLoreError(f"{source}: every fragment must be an object")
    key = raw.get("id")
    text = raw.get("text")
    # ``weight`` replaced ``tier``; older seed files still say tier.
    weight = raw.get("weight", LEGACY_TIER_WEIGHTS.get(str(raw.get("tier")), raw.get("tier")))
    themes = raw.get("themes", [])
    if not isinstance(key, str) or not is_fragment_key(key):
        raise PresetLoreError(f"{source}: invalid fragment id {key!r}")
    if not isinstance(text, str) or not text.strip() or len(text) > FRAGMENT_MAX_CHARS:
        raise PresetLoreError(f"{source}: fragment {key} text is empty or too long")
    if weight not in LORE_WEIGHTS:
        raise PresetLoreError(f"{source}: fragment {key} has invalid weight {weight!r}")
    if not isinstance(themes, list) or not all(isinstance(item, str) for item in themes):
        raise PresetLoreError(f"{source}: fragment {key} themes must be strings")
    refs = raw.get("refs", [])
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        raise PresetLoreError(f"{source}: fragment {key} refs must be strings")
    return LoreFragment(
        key=key,
        text=text.strip(),
        themes=normalize_themes(themes),
        weight=cast(LoreWeight, weight),
        refs=tuple(dict.fromkeys(item.strip() for item in refs if item.strip())),
    )


def parse_preset(raw: Any, source: str) -> PresetStory:
    """Validate one decoded canonical (English) preset document."""
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise PresetLoreError(f"{source}: expected an object with schema 1")
    preset_id = raw.get("id")
    name = raw.get("name")
    persona = raw.get("persona")
    fragments = raw.get("fragments")
    if not isinstance(preset_id, str) or not is_fragment_key(preset_id):
        raise PresetLoreError(f"{source}: invalid preset id")
    if not isinstance(name, str) or not name.strip():
        raise PresetLoreError(f"{source}: missing name")
    if not isinstance(persona, str) or not persona.strip() or len(persona) > PERSONA_MAX_CHARS:
        raise PresetLoreError(f"{source}: persona is empty or too long")
    if not isinstance(fragments, list):
        raise PresetLoreError(f"{source}: fragments must be a list")
    parsed = tuple(_fragment(item, source) for item in fragments)
    keys = [fragment.key for fragment in parsed]
    if len(keys) != len(set(keys)):
        raise PresetLoreError(f"{source}: duplicate fragment ids")
    return PresetStory(
        preset_id=preset_id,
        name=name.strip(),
        persona=persona.strip(),
        fragments=parsed,
    )


def apply_translation(base: PresetStory, raw: Any, source: str) -> PresetStory:
    """Overlay one translation on the English story, falling back per item."""
    if not isinstance(raw, dict):
        raise PresetLoreError(f"{source}: expected an object")
    if raw.get("id") not in (None, base.preset_id):
        raise PresetLoreError(f"{source}: id must match the English preset")
    name = raw.get("name")
    persona = raw.get("persona")
    texts: dict[str, str] = {}
    for item in raw.get("fragments") or []:
        if not isinstance(item, dict):
            raise PresetLoreError(f"{source}: every fragment must be an object")
        key = item.get("id")
        text = item.get("text")
        if not isinstance(key, str) or not isinstance(text, str):
            raise PresetLoreError(f"{source}: fragments need string id and text")
        if text.strip() and len(text) <= FRAGMENT_MAX_CHARS:
            texts[key] = text.strip()
    return PresetStory(
        preset_id=base.preset_id,
        name=name.strip() if isinstance(name, str) and name.strip() else base.name,
        persona=(
            persona.strip()
            if isinstance(persona, str) and persona.strip() and len(persona) <= PERSONA_MAX_CHARS
            else base.persona
        ),
        fragments=tuple(
            replace(fragment, text=texts.get(fragment.key, fragment.text))
            for fragment in base.fragments
        ),
    )


@lru_cache(maxsize=8)
def load_presets(
    locale: str = "en",
    directory: Path = LORE_DIRECTORY,
) -> dict[str, PresetStory]:
    """Return every shipped preset story for ``locale``, keyed by preset id."""
    presets: dict[str, PresetStory] = {}
    entities = _canon_entities(directory)
    for path in sorted(directory.glob("*.json")):
        if path.name in _RESERVED_FILES:
            continue
        preset = parse_preset(json.loads(path.read_text(encoding="utf-8")), path.name)
        if preset.preset_id != path.stem:
            raise PresetLoreError(f"{path.name}: id must match the file name")
        if entities is not None:
            for fragment in preset.fragments:
                unknown = [ref for ref in fragment.refs if ref not in entities]
                if unknown:
                    raise PresetLoreError(
                        f"{path.name}: fragment {fragment.key} refs unknown canon {unknown}"
                    )
        if locale != "en" and locale in STORY_LOCALES:
            translated = directory / locale / path.name
            if translated.exists():
                preset = apply_translation(
                    preset,
                    json.loads(translated.read_text(encoding="utf-8")),
                    f"{locale}/{path.name}",
                )
        presets[preset.preset_id] = preset
    return presets


def get_preset(preset_id: str, locale: str = "en") -> PresetStory | None:
    """Return one shipped preset story in ``locale``, or ``None`` when unknown."""
    return load_presets(locale).get(preset_id)


__all__ = [
    "LORE_DIRECTORY",
    "PresetLoreError",
    "apply_translation",
    "get_preset",
    "load_presets",
    "parse_preset",
]
