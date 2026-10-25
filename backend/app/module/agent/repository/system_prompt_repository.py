"""Short-lived persistence for ordered system prompt sections.

The agent service creates conversations outside a request-scoped transaction and
the SSE loop must never hold a database session. This repository therefore opens
one small session per operation instead of accepting ``AsyncSession``.
"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.module.agent.domain.system_prompt_domain import SystemPromptSection
from app.module.agent.model.system_prompt_model import SystemPromptSectionModel


def _record(row: SystemPromptSectionModel) -> SystemPromptSection:
    """Snapshot an ORM row so the caller never observes a detached instance."""
    return SystemPromptSection(
        id=row.id,
        title=row.title,
        body=row.body,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SystemPromptRepository:
    """CRUD and locked reordering for owner-authored prompt sections."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_sections(self) -> list[SystemPromptSection]:
        """Return every section in display order.

        ``id`` is the tie-breaker so rows sharing ``sort_order`` never swap
        places between a database read and a cached response. 顯示順序固定為
        ``sort_order, id``，快取內容與對話組裝都依賴這個穩定順序。
        """
        async with self.session_factory() as session:
            statement = select(SystemPromptSectionModel).order_by(
                SystemPromptSectionModel.sort_order,
                SystemPromptSectionModel.id,
            )
            rows = (await session.execute(statement)).scalars().all()
            return [_record(row) for row in rows]

    async def get_section(self, section_id: int) -> SystemPromptSection | None:
        async with self.session_factory() as session:
            row = await session.get(SystemPromptSectionModel, section_id)
            return _record(row) if row is not None else None

    async def next_sort_order(self) -> int:
        """Return the append position, leaving gaps of 10 between sections."""
        async with self.session_factory() as session:
            statement = select(func.coalesce(func.max(SystemPromptSectionModel.sort_order), 0))
            maximum = (await session.execute(statement)).scalar_one()
            return int(maximum) + 10

    async def create_section(
        self,
        *,
        title: str,
        body: str,
        sort_order: int,
        now: datetime,
    ) -> SystemPromptSection:
        async with self.session_factory() as session:
            async with session.begin():
                row = SystemPromptSectionModel(
                    title=title,
                    body=body,
                    sort_order=sort_order,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()
                return _record(row)

    async def update_section(
        self,
        section_id: int,
        *,
        title: str,
        body: str,
        sort_order: int,
        now: datetime,
    ) -> SystemPromptSection | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(SystemPromptSectionModel, section_id)
                if row is None:
                    return None
                row.title = title
                row.body = body
                row.sort_order = sort_order
                row.updated_at = now
                await session.flush()
                return _record(row)

    async def delete_section(self, section_id: int) -> bool:
        """Hard-delete one section; the identity sequence is never rewound."""
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(SystemPromptSectionModel, section_id)
                if row is None:
                    return False
                await session.delete(row)
                await session.flush()
                return True

    async def reorder_sections(
        self,
        section_ids: list[int],
        *,
        now: datetime,
    ) -> list[SystemPromptSection]:
        """Rewrite ``sort_order`` in one locked transaction.

        ``FOR UPDATE`` serializes concurrent reorders. 驗證必須在鎖定之後才
        進行：若先讀 ids 再鎖，另一個交易可能在中間新增或刪除 section，
        造成「驗證通過但寫入遺漏」的競態。新的 sort_order 採 ``(index + 1)
        * 10``，保留手動插入或未來拖曳中斷時的整數空隙。
        """
        async with self.session_factory() as session:
            async with session.begin():
                statement = (
                    select(SystemPromptSectionModel)
                    .order_by(
                        SystemPromptSectionModel.sort_order,
                        SystemPromptSectionModel.id,
                    )
                    .with_for_update()
                )
                rows = list((await session.execute(statement)).scalars().all())
                existing_ids = {row.id for row in rows}
                requested_ids = set(section_ids)
                # 傳入清單必須恰好覆蓋現有全部 section：不重複、不遺漏，
                # 也不能包含已刪除或從未存在的 id。
                if len(section_ids) != len(requested_ids) or requested_ids != existing_ids:
                    raise ValueError(
                        "The reorder payload must list every existing system "
                        "prompt section exactly once."
                    )

                rows_by_id = {row.id: row for row in rows}
                for index, section_id in enumerate(section_ids):
                    row = rows_by_id[section_id]
                    row.sort_order = (index + 1) * 10
                    row.updated_at = now
                await session.flush()
                return [_record(rows_by_id[section_id]) for section_id in section_ids]

    async def clear_sections(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(delete(SystemPromptSectionModel))


__all__ = ["SystemPromptRepository"]
