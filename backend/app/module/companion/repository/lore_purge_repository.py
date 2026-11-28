"""Remove lore an earlier canon left behind, across every account.

When the shipped lore changes (a new canon), three kinds of rows can keep the
old script alive: seeded items the seeder retired, per-account copies of old
seeded text that the account never edited, and progress rows that point at
fragments that no longer exist. This repository deletes exactly those; it never
touches anything a person wrote or edited:

- retired *seeded* lore items (``seed_hash`` set, not ``admin_modified``) and,
  through the foreign key, their texts;
- told-progress rows of a preset companion whose fragment is no longer an active
  preset item, an account's own fragment (``u-``), a life story (``g-``), or a
  fragment root added for that account;
- unedited copy-on-write fragments of a preset story whose fragment is no longer
  an active item (deleted) or whose text differs from the live item (refreshed to
  the live text, in the story's locale or English);
- copy-on-write stories that hold no edited and no own fragment any more (reset,
  so the live preset lore applies again);
- published or draft life stories whose text retells the old canon (marked
  ``retired``, never deleted);
- root's per-account ``replace``/``hide`` overrides of fragments that no longer
  exist, and ``replace`` overrides whose text is exactly an old seeded text that
  was just superseded (passed in as ``superseded``).

It must run on a session that bypasses row-level security (the owner
maintenance session or a migration), because it spans accounts. Every statement
is idempotent. Callers log counts only.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.companion.domain.seed_domain import SupersededText

# Active preset items, keyed for joins: (preset_id, fragment_key).
_ACTIVE_ITEM = (
    "SELECT 1 FROM companion_lore_item i "
    "WHERE i.retired_at IS NULL AND i.preset_id = {preset} AND i.fragment_key = {key}"
)

DELETE_RETIRED_ITEMS_SQL = (
    "DELETE FROM companion_lore_item "
    "WHERE retired_at IS NOT NULL AND seed_hash IS NOT NULL AND NOT admin_modified"
)

DELETE_STALE_TOLD_SQL = (
    "DELETE FROM companion_lore_told t "
    "WHERE t.companion_ref LIKE 'preset:%' "
    "AND t.fragment_key NOT LIKE 'u-%' AND t.fragment_key NOT LIKE 'g-%' "
    "AND NOT EXISTS ("
    + _ACTIVE_ITEM.format(preset="substr(t.companion_ref, 8)", key="t.fragment_key")
    + ") AND NOT EXISTS ("
    "SELECT 1 FROM companion_admin_lore_override o "
    "WHERE o.user_id = t.user_id AND o.companion_ref = t.companion_ref "
    "AND o.fragment_key = t.fragment_key AND o.action = 'add')"
)

DELETE_STALE_COPIES_SQL = (
    "DELETE FROM companion_lore_fragment f USING companion_story s "
    "WHERE s.id = f.story_id AND s.user_id = f.user_id AND s.preset_id IS NOT NULL "
    "AND NOT f.edited AND f.fragment_key NOT LIKE 'u-%' "
    "AND NOT EXISTS (" + _ACTIVE_ITEM.format(preset="s.preset_id", key="f.fragment_key") + ")"
)

REFRESH_COPIES_SQL = (
    "UPDATE companion_lore_fragment f "
    "SET text = live.text, weight = live.weight, themes = live.themes, refs = live.refs "
    "FROM ("
    "  SELECT s.id AS story_id, s.user_id, i.fragment_key, i.weight, i.themes, i.refs, "
    "  COALESCE("
    "    (SELECT tx.text FROM companion_lore_item_text tx "
    "     WHERE tx.item_id = i.id AND tx.locale = s.locale),"
    "    (SELECT tx.text FROM companion_lore_item_text tx "
    "     WHERE tx.item_id = i.id AND tx.locale = 'en')"
    "  ) AS text "
    "  FROM companion_story s "
    "  JOIN companion_lore_item i ON i.preset_id = s.preset_id AND i.retired_at IS NULL "
    "  WHERE s.preset_id IS NOT NULL"
    ") AS live "
    "WHERE f.story_id = live.story_id AND f.user_id = live.user_id "
    "AND f.fragment_key = live.fragment_key AND NOT f.edited "
    "AND live.text IS NOT NULL AND f.text IS DISTINCT FROM live.text"
)

RESET_EMPTY_STORIES_SQL = (
    "WITH idle AS ("
    "  SELECT s.id, s.user_id FROM companion_story s "
    "  WHERE s.preset_id IS NOT NULL AND s.lore_customized "
    "  AND NOT EXISTS (SELECT 1 FROM companion_lore_fragment f "
    "    WHERE f.story_id = s.id AND f.user_id = s.user_id "
    "    AND (f.edited OR f.fragment_key LIKE 'u-%'))"
    "), cleared AS ("
    "  DELETE FROM companion_lore_fragment f USING idle "
    "  WHERE f.story_id = idle.id AND f.user_id = idle.user_id"
    ") "
    "UPDATE companion_story s SET lore_customized = false FROM idle "
    "WHERE s.id = idle.id AND s.user_id = idle.user_id"
)

DELETE_STALE_OVERRIDES_SQL = (
    "DELETE FROM companion_admin_lore_override o "
    "WHERE o.companion_ref LIKE 'preset:%' AND o.action IN ('replace', 'hide') "
    "AND NOT EXISTS ("
    + _ACTIVE_ITEM.format(preset="substr(o.companion_ref, 8)", key="o.fragment_key")
    + ")"
)

# Life stories written before the canon changed may retell the old script (the
# librarians "giving" their faces). They are retired, never deleted: root can
# still read or delete them, but they no longer surface.
OLD_CANON_STORY_PATTERN = (
    r"(press|gave|give|giving)[^.。]{0,60}face[^.。]{0,80}lintel"
    r"|face-giving|remember everyone except|把臉|把脸|臉壓進|脸压进|獻出.{0,6}臉|献出.{0,6}脸"
)
RETIRE_OLD_CANON_STORIES_SQL = (
    "UPDATE companion_generated_story SET status = 'retired' "
    "WHERE status <> 'retired' AND (text ~* :pattern OR title ~* :pattern)"
)

DELETE_SUPERSEDED_OVERRIDES_SQL = (
    "DELETE FROM companion_admin_lore_override o "
    "WHERE o.companion_ref = :ref AND o.fragment_key = :key AND o.locale = :locale "
    "AND o.action = 'replace' AND o.text = :old_text"
)


@dataclass
class LorePurgeResult:
    """How many rows each purge step touched (counts only, never content)."""

    retired_items: int = 0
    told_rows: int = 0
    stale_copies: int = 0
    refreshed_copies: int = 0
    reset_stories: int = 0
    overrides: int = 0
    retired_stories: int = 0

    @property
    def total(self) -> int:
        return (
            self.retired_items
            + self.told_rows
            + self.stale_copies
            + self.refreshed_copies
            + self.reset_stories
            + self.overrides
            + self.retired_stories
        )


class LorePurgeRepository:
    """Delete or refresh rows that keep an old canon alive (RLS-bypassing session)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _run(self, statement: str, params: dict[str, str] | None = None) -> int:
        result = await self.session.execute(text(statement), params or {})
        return int(getattr(result, "rowcount", 0) or 0)

    async def purge(self, superseded: Sequence[SupersededText] = ()) -> LorePurgeResult:
        """Run every step; ``superseded`` lists seeded texts the seed just replaced."""
        result = LorePurgeResult()
        for item in superseded:
            result.overrides += await self._run(
                DELETE_SUPERSEDED_OVERRIDES_SQL,
                {
                    "ref": f"preset:{item.preset_id}",
                    "key": item.fragment_key,
                    "locale": item.locale,
                    "old_text": item.old_text,
                },
            )
        result.retired_items = await self._run(DELETE_RETIRED_ITEMS_SQL)
        result.told_rows = await self._run(DELETE_STALE_TOLD_SQL)
        result.stale_copies = await self._run(DELETE_STALE_COPIES_SQL)
        result.refreshed_copies = await self._run(REFRESH_COPIES_SQL)
        result.reset_stories = await self._run(RESET_EMPTY_STORIES_SQL)
        result.overrides += await self._run(DELETE_STALE_OVERRIDES_SQL)
        result.retired_stories = await self._run(
            RETIRE_OLD_CANON_STORIES_SQL,
            {"pattern": OLD_CANON_STORY_PATTERN},
        )
        return result


__all__ = [
    "DELETE_RETIRED_ITEMS_SQL",
    "DELETE_STALE_COPIES_SQL",
    "DELETE_STALE_OVERRIDES_SQL",
    "DELETE_STALE_TOLD_SQL",
    "DELETE_SUPERSEDED_OVERRIDES_SQL",
    "OLD_CANON_STORY_PATTERN",
    "REFRESH_COPIES_SQL",
    "RESET_EMPTY_STORIES_SQL",
    "RETIRE_OLD_CANON_STORIES_SQL",
    "LorePurgeRepository",
    "LorePurgeResult",
]
