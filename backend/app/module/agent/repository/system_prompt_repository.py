"""Short-lived persistence for ordered system prompt sections.

The agent service creates conversations outside a request-scoped transaction and
the SSE loop must never hold a database session. This repository therefore opens
one small session per operation instead of accepting ``AsyncSession``.

Every row is equal. Seeded defaults and owner-authored sections share the same
table and the same CRUD surface; there is no built-in override lookup and no
Python-only fallback at read time.
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
    """CRUD and locked reordering for every prompt section."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_sections(self) -> list[SystemPromptSection]:
        """Return every section in display order.

        ``id`` is the tie-breaker so rows sharing ``sort_order`` never swap
        places between a database read and a cached response. The display order
        is fixed at ``sort_order, id``; both the cache payload and conversation
        composition depend on that stable order.
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
            statement = select(SystemPromptSectionModel).where(
                SystemPromptSectionModel.id == section_id
            )
            row = (await session.execute(statement)).scalar_one_or_none()
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
                statement = select(SystemPromptSectionModel).where(
                    SystemPromptSectionModel.id == section_id
                )
                row = (await session.execute(statement)).scalar_one_or_none()
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
                statement = select(SystemPromptSectionModel).where(
                    SystemPromptSectionModel.id == section_id
                )
                row = (await session.execute(statement)).scalar_one_or_none()
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

        ``FOR UPDATE`` serializes concurrent reorders. Validation must happen
        after the lock: reading ids first would let another transaction insert
        or delete a row in between, producing a payload that passes validation
        but leaves a section out. New orders use ``(index + 1) * 10`` so manual
        inserts and interrupted drags keep integer gaps.
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
                # The payload must cover every existing section exactly once:
                # no duplicates, no omissions, and no deleted or unknown ids.
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

    async def replace_with_defaults(
        self,
        defaults: list[dict[str, str]],
        *,
        now: datetime,
    ) -> list[SystemPromptSection]:
        """Replace the complete collection with the seeded default sections.

        Reset is intentionally destructive: custom rows are removed too, and the
        four defaults are inserted as ordinary rows with fresh identities. The
        delete and insert share one transaction so a concurrent list never sees
        a half-reset collection.
        """
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(delete(SystemPromptSectionModel))
                rows: list[SystemPromptSectionModel] = []
                for index, section in enumerate(defaults, start=1):
                    row = SystemPromptSectionModel(
                        title=section["title"],
                        body=section["body"],
                        sort_order=index * 10,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    rows.append(row)
                await session.flush()
                return [_record(row) for row in rows]


__all__ = ["SystemPromptRepository"]
