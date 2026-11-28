"""Seed bodies of the life-story prompt templates.

The live templates are root-editable and served by the config provider. These
files under ``lore/seed/templates/`` are the shipped seed the database store
starts from, and the fallback when no store is installed (tests, a fresh
process before seeding).
"""

from functools import cache
from pathlib import Path

from app.module.companion.service.preset_lore_catalog import LORE_DIRECTORY

SEED_TEMPLATE_DIRECTORY = LORE_DIRECTORY / "seed" / "templates"


@cache
def seed_template(key: str, locale: str = "en", directory: Path = SEED_TEMPLATE_DIRECTORY) -> str:
    """Return the seed body of template ``key`` (empty when none is shipped)."""
    for candidate in (f"{key}.{locale}.md", f"{key}.en.md"):
        path = directory / candidate
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return ""


__all__ = ["SEED_TEMPLATE_DIRECTORY", "seed_template"]
