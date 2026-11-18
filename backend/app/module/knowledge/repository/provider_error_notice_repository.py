"""SQLAlchemy persistence for global provider-error notices.

Every method uses the short-lived system session opened by the service. The
repository itself never commits; the session context owns the transaction.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.provider_error_notice_model import (
    ProviderErrorNoticeModel,
)


class ProviderErrorNoticeRepository:
    """One global notice table; no owner scoping because it holds no private rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, notice: ProviderErrorNoticeModel) -> ProviderErrorNoticeModel:
        self.session.add(notice)
        await self.session.flush()
        return notice

    async def get_by_id(self, notice_id: int) -> ProviderErrorNoticeModel | None:
        statement = select(ProviderErrorNoticeModel).where(
            ProviderErrorNoticeModel.id == notice_id
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def find_recent_unresolved(
        self,
        *,
        capability: str,
        operation: str,
        error_code: str,
        since: datetime,
    ) -> ProviderErrorNoticeModel | None:
        """Find one unresolved notice with the same fingerprint inside the window."""
        statement = (
            select(ProviderErrorNoticeModel)
            .where(
                ProviderErrorNoticeModel.capability == capability,
                ProviderErrorNoticeModel.operation == operation,
                ProviderErrorNoticeModel.error_code == error_code,
                ProviderErrorNoticeModel.resolved_at.is_(None),
                ProviderErrorNoticeModel.last_seen_at >= since,
            )
            .order_by(ProviderErrorNoticeModel.last_seen_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_notices(
        self,
        *,
        include_resolved: bool,
        limit: int,
    ) -> Sequence[ProviderErrorNoticeModel]:
        statement = select(ProviderErrorNoticeModel)
        if not include_resolved:
            statement = statement.where(ProviderErrorNoticeModel.resolved_at.is_(None))
        statement = statement.order_by(
            ProviderErrorNoticeModel.last_seen_at.desc(),
            ProviderErrorNoticeModel.id.desc(),
        ).limit(limit)
        return list((await self.session.execute(statement)).scalars().all())

    async def count_unresolved(self) -> int:
        statement = select(func.count()).select_from(ProviderErrorNoticeModel).where(
            ProviderErrorNoticeModel.resolved_at.is_(None)
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def resolve(
        self,
        notice: ProviderErrorNoticeModel,
        *,
        user_id: int,
        now: datetime,
    ) -> ProviderErrorNoticeModel:
        notice.resolved_at = now
        notice.resolved_by_user_id = user_id
        await self.session.flush()
        return notice

    async def resolve_all(self, *, user_id: int, now: datetime) -> int:
        statement = (
            update(ProviderErrorNoticeModel)
            .where(ProviderErrorNoticeModel.resolved_at.is_(None))
            .values(resolved_at=now, resolved_by_user_id=user_id)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["ProviderErrorNoticeRepository"]
