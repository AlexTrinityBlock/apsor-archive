"""Generic SQLAlchemy persistence for the four provider capability tables.

All CRUD methods take a :class:`ProviderTableSpec`; no per-capability repository
subclass exists. ``list_active`` walks the four specs once so ``AiRuntime`` can
build a full snapshot from a single repository instance.

Each capability is an ordered chain. ``is_active`` means "member of the chain"
and ``priority`` is its zero-based position; the partial unique index on
``priority WHERE is_active`` keeps two active rows from sharing a slot. Inactive
rows keep a saved configuration and any old priority value.
"""

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.domain.provider_config_domain import (
    PROVIDER_TABLE_SPECS,
    ProviderTableSpec,
)
from app.module.knowledge.model.provider_config_model import ProviderConfigMixin
from app.shared.time import utcnow


class ProviderConfigRepository:
    """One row set per capability, all accessed through ``ProviderTableSpec``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def flush(self) -> None:
        """Flush pending state without committing; the request owns the commit."""
        await self.session.flush()

    async def get_by_id(
        self,
        spec: ProviderTableSpec,
        provider_id: int,
    ) -> ProviderConfigMixin | None:
        statement = select(spec.model).where(spec.model.id == provider_id)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_active(self, spec: ProviderTableSpec) -> ProviderConfigMixin | None:
        """Return the primary (lowest-priority) active row for one capability.

        This is the compatibility accessor: callers that only need "the"
        configured provider keep receiving the head of the chain. ``AiRuntime``
        uses :meth:`list_active_chain` to build fallbacks.
        """
        statement = (
            select(spec.model)
            .where(spec.model.is_active.is_(True))
            .order_by(spec.model.priority, spec.model.id)
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_active_chain(
        self,
        spec: ProviderTableSpec,
    ) -> Sequence[ProviderConfigMixin]:
        """Return one capability's active chain, primary first."""
        statement = (
            select(spec.model)
            .where(spec.model.is_active.is_(True))
            .order_by(spec.model.priority, spec.model.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_all(self, spec: ProviderTableSpec) -> Sequence[ProviderConfigMixin]:
        statement = select(spec.model).order_by(spec.model.id)
        return list((await self.session.execute(statement)).scalars().all())

    async def list_active(self) -> Sequence[ProviderConfigMixin]:
        """Return every active row across the four tables, in capability order."""
        active: list[ProviderConfigMixin] = []
        for spec in PROVIDER_TABLE_SPECS.values():
            active.extend(await self.list_active_chain(spec))
        return active

    async def save(self, row: ProviderConfigMixin) -> ProviderConfigMixin:
        self.session.add(row)
        # Flush first so the identity id and the chain index are checked by the
        # database before the runtime reload happens.
        await self.session.flush()
        return row

    async def delete(self, row: ProviderConfigMixin) -> None:
        await self.session.delete(row)
        await self.session.flush()

    async def deactivate_all(self, spec: ProviderTableSpec) -> None:
        statement = (
            update(spec.model)
            .where(spec.model.is_active.is_(True))
            .values(is_active=False, updated_at=utcnow())
        )
        await self.session.execute(statement)

    async def deactivate_row(self, row: ProviderConfigMixin) -> None:
        """Remove one row from the chain without touching the others."""
        if not row.is_active:
            return
        row.is_active = False
        row.updated_at = utcnow()
        await self.session.flush()

    async def replace_chain(
        self,
        spec: ProviderTableSpec,
        rows: Sequence[ProviderConfigMixin],
    ) -> None:
        """Rewrite one capability's chain to exactly ``rows``.

        The operation is deliberately two-phase: every active row is first
        deactivated (so the partial unique index has no live values to clash
        with), then each ordered row receives its new zero-based priority and is
        reactivated. The caller owns the surrounding transaction.
        """
        await self.deactivate_all(spec)
        now = utcnow()
        for priority, row in enumerate(rows):
            row.priority = priority
            row.is_active = True
            row.updated_at = now
        await self.session.flush()


__all__ = ["ProviderConfigRepository"]
