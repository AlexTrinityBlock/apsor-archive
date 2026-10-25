"""Generic SQLAlchemy persistence for the four provider capability tables.

All CRUD methods take a :class:`ProviderTableSpec`; no per-capability repository
subclass exists.  ``list_active`` walks the four specs once so ``AiRuntime`` can
build a full snapshot from a single repository instance.
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
        """Return the single active row for one capability, if any.

        partial unique index 保證最多一列，所以用最嚴格的
        ``scalar_one_or_none``；若真的出現兩列，寧可報錯也不要默默選一列。
        """
        statement = select(spec.model).where(spec.model.is_active.is_(True))
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_all(self, spec: ProviderTableSpec) -> Sequence[ProviderConfigMixin]:
        statement = select(spec.model).order_by(spec.model.id)
        return list((await self.session.execute(statement)).scalars().all())

    async def list_active(self) -> Sequence[ProviderConfigMixin]:
        """Return every active row across the four tables, in fixed order."""
        active: list[ProviderConfigMixin] = []
        for spec in PROVIDER_TABLE_SPECS.values():
            row = await self.get_active(spec)
            if row is not None:
                active.append(row)
        return active

    async def save(self, row: ProviderConfigMixin) -> ProviderConfigMixin:
        self.session.add(row)
        # 先 flush，讓 identity id 與 partial unique index 在 runtime reload 前
        # 就完成資料庫端檢查。
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

    async def deactivate_others(
        self,
        spec: ProviderTableSpec,
        *,
        keep_id: int,
    ) -> None:
        statement = (
            update(spec.model)
            .where(
                spec.model.is_active.is_(True),
                spec.model.id != keep_id,
            )
            .values(is_active=False, updated_at=utcnow())
        )
        await self.session.execute(statement)


__all__ = ["ProviderConfigRepository"]
