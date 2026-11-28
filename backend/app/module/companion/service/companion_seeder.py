"""Apply the shipped companion seed bundle to the database, idempotently.

Run once per process start (API lifespan and worker). Under a transaction
advisory lock it compares the bundle's ``content_hash`` with
``companion_seed_state``; when they match it does nothing (one SELECT).
Otherwise, row by row:

- a missing row is inserted with ``seed_hash`` set;
- a row root has **not** edited (``admin_modified = false``) whose shipped text
  changed is updated in place;
- a row root **has** edited keeps root's version; the new shipped hash is
  recorded in ``upstream_seed_hash`` so the admin UI can offer "review";
- seeded lore items that disappeared from the bundle are retired (never
  deleted, so told progress keeps its meaning); seeded presets that
  disappeared are disabled.

Every applied change bumps ``companion_seed_state.content_version`` (and the
config row's ``version``) so the providers in every process reload.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.companion.domain.seed_domain import SEED_BUNDLE
from app.module.companion.model.companion_world_model import (
    CompanionCanonEntityModel,
    CompanionConfigModel,
    CompanionLoreItemModel,
    CompanionLoreItemTextModel,
    CompanionPresetModel,
    CompanionPresetTextModel,
    CompanionPromptTemplateModel,
    CompanionSeedStateModel,
    CompanionWorldDocModel,
)
from app.module.companion.service.seed_catalog import SeedBundle, load_seed_bundle
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

# A fixed 64-bit key for pg_advisory_xact_lock (seeding is cluster-wide).
_ADVISORY_LOCK_KEY = 0x41505352_434D5053  # "APSRCMPS"


@dataclass
class SeedResult:
    """What one seeding pass did."""

    applied: bool = False
    inserted: int = 0
    updated: int = 0
    flagged: int = 0
    retired: int = 0
    content_version: int = 0


def _payload(row: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {name: value for name, value in row.items() if name not in keys and name != "seed_hash"}


class CompanionSeeder:
    """Write the seed bundle into the global companion tables."""

    def __init__(self, bundle: SeedBundle | None = None) -> None:
        self.bundle = bundle or load_seed_bundle()

    async def run(self, database: Database) -> SeedResult:
        """Seed in one root transaction; a no-op when the bundle is unchanged."""
        async with database.system_session() as session:
            return await self.apply(session)

    async def apply(self, session: AsyncSession) -> SeedResult:
        """Seed on an open session that may write global configuration."""
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _ADVISORY_LOCK_KEY},
        )
        state = await session.get(CompanionSeedStateModel, SEED_BUNDLE)
        result = SeedResult(content_version=state.content_version if state else 0)
        if state is not None and state.content_hash == self.bundle.content_hash:
            return result
        await self._presets(session, result)
        await self._simple(
            session,
            CompanionPresetTextModel,
            self.bundle.rows["companion_preset_text"],
            ("preset_id", "locale"),
            result,
        )
        await self._lore(session, result)
        await self._simple(
            session,
            CompanionCanonEntityModel,
            self.bundle.rows["companion_canon_entity"],
            ("entity_id", "locale"),
            result,
        )
        await self._simple(
            session,
            CompanionWorldDocModel,
            self.bundle.rows["companion_world_doc"],
            ("doc_key", "locale"),
            result,
            versioned=True,
        )
        await self._simple(
            session,
            CompanionPromptTemplateModel,
            self.bundle.rows["companion_prompt_template"],
            ("template_key", "locale"),
            result,
            versioned=True,
        )
        await self._config(session, result)
        now = utcnow()
        if state is None:
            state = CompanionSeedStateModel(
                bundle=SEED_BUNDLE,
                content_hash=self.bundle.content_hash,
                content_version=1,
                applied_at=now,
            )
            session.add(state)
        else:
            state.content_hash = self.bundle.content_hash
            state.content_version += 1
            state.applied_at = now
        await session.flush()
        result.applied = True
        result.content_version = state.content_version
        logger.info(
            "companion seed applied inserted=%s updated=%s flagged=%s retired=%s",
            result.inserted,
            result.updated,
            result.flagged,
            result.retired,
        )
        return result

    # --- generic row reconciliation ---------------------------------------

    @staticmethod
    def _reconcile(
        model: Any,
        row: dict[str, Any],
        keys: Sequence[str],
        result: SeedResult,
        *,
        versioned: bool = False,
    ) -> None:
        """Apply one seed row to an existing ORM object per the edit rules."""
        new_hash = row["seed_hash"]
        if model.seed_hash == new_hash:
            if model.upstream_seed_hash is not None and not model.admin_modified:
                model.upstream_seed_hash = None
            return
        if model.admin_modified:
            if model.upstream_seed_hash != new_hash:
                model.upstream_seed_hash = new_hash
                result.flagged += 1
            return
        for name, value in _payload(row, keys).items():
            setattr(model, name, value)
        model.seed_hash = new_hash
        model.upstream_seed_hash = None
        if versioned:
            model.version = (model.version or 0) + 1
        result.updated += 1

    async def _simple(
        self,
        session: AsyncSession,
        model_type: Any,
        rows: Sequence[dict[str, Any]],
        keys: Sequence[str],
        result: SeedResult,
        *,
        versioned: bool = False,
    ) -> None:
        existing = {
            tuple(getattr(item, key) for key in keys): item
            for item in (await session.scalars(select(model_type))).all()
        }
        for row in rows:
            identity = tuple(row[key] for key in keys)
            current = existing.get(identity)
            if current is None:
                session.add(model_type(**row, admin_modified=False))
                result.inserted += 1
            else:
                self._reconcile(current, row, keys, result, versioned=versioned)
        await session.flush()

    async def _presets(self, session: AsyncSession, result: SeedResult) -> None:
        rows = self.bundle.rows["companion_preset"]
        existing = {item.id: item for item in (await session.scalars(select(CompanionPresetModel)))}
        has_default = any(item.is_global_default for item in existing.values())
        shipped = {row["id"] for row in rows}
        for row in rows:
            current = existing.get(row["id"])
            values = dict(row)
            if has_default:
                # Never move root's chosen global default; only seed it once.
                values["is_global_default"] = (
                    current.is_global_default if current is not None else False
                )
            if current is None:
                session.add(CompanionPresetModel(**values, admin_modified=False))
                result.inserted += 1
            else:
                self._reconcile(current, values, ("id",), result)
        for preset_id, current in existing.items():
            if preset_id not in shipped and current.seed_hash and not current.admin_modified:
                if current.enabled:
                    current.enabled = False
                    current.is_global_default = False
                    result.retired += 1
        await session.flush()

    async def _lore(self, session: AsyncSession, result: SeedResult) -> None:
        items = {
            (item.preset_id, item.fragment_key): item
            for item in (await session.scalars(select(CompanionLoreItemModel))).all()
        }
        shipped: set[tuple[str, str]] = set()
        for row in self.bundle.rows["companion_lore_item"]:
            identity = (row["preset_id"], row["fragment_key"])
            shipped.add(identity)
            current = items.get(identity)
            if current is None:
                current = CompanionLoreItemModel(**row, admin_modified=False)
                session.add(current)
                items[identity] = current
                result.inserted += 1
            else:
                if current.retired_at is not None and current.seed_hash is not None:
                    current.retired_at = None
                self._reconcile(current, row, ("preset_id", "fragment_key"), result)
        now = utcnow()
        for identity, current in items.items():
            if identity not in shipped and current.seed_hash and current.retired_at is None:
                current.retired_at = now
                result.retired += 1
        await session.flush()
        texts = {
            (row.item_id, row.locale): row
            for row in (await session.scalars(select(CompanionLoreItemTextModel))).all()
        }
        for row in self.bundle.rows["companion_lore_item_text"]:
            item = items[(row["preset_id"], row["fragment_key"])]
            values = {
                "item_id": item.id,
                "locale": row["locale"],
                "text": row["text"],
                "seed_hash": row["seed_hash"],
            }
            current_text = texts.get((item.id, row["locale"]))
            if current_text is None:
                session.add(CompanionLoreItemTextModel(**values, admin_modified=False))
                result.inserted += 1
            else:
                self._reconcile(current_text, values, ("item_id", "locale"), result)
        await session.flush()

    async def _config(self, session: AsyncSession, result: SeedResult) -> None:
        row = self.bundle.rows["companion_config"][0]
        current = await session.get(CompanionConfigModel, 1)
        if current is None:
            session.add(CompanionConfigModel(**row, admin_modified=False, version=1))
            result.inserted += 1
        else:
            before = result.updated
            self._reconcile(current, row, ("id",), result)
            if result.updated != before:
                current.version = (current.version or 0) + 1
        await session.flush()


async def seed_companion_world(database: Database) -> SeedResult:
    """Apply the shipped seed bundle (the API lifespan and worker startup call this)."""
    return await CompanionSeeder().run(database)


__all__ = ["CompanionSeeder", "SeedResult", "seed_companion_world"]
