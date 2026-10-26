"""SQLAlchemy persistence for files.

Every repository instance is bound to one owner. Reads and writes always carry
``user_id = :user_id`` even though row-level security already scopes the
transaction: the SQL predicate is the primary isolation boundary and RLS is the
defense-in-depth layer.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.file_model import FileModel
from app.shared.time import utcnow


class FileRepository:
    """Queries over one owner's file table; no business decisions live here."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def add(self, file: FileModel) -> FileModel:
        file.user_id = self.user_id
        self.session.add(file)
        await self.session.flush()
        return file

    async def flush(self) -> None:
        await self.session.flush()

    async def mark_not_current(self, file: FileModel) -> None:
        file.is_current = False
        file.updated_at = utcnow()
        await self.session.flush()

    async def delete(self, file: FileModel) -> None:
        """Remove an unpublished file row after a failed ingestion."""
        await self.session.delete(file)
        await self.session.flush()

    async def update_location(
        self,
        file: FileModel,
        *,
        path: str,
        file_name: str,
    ) -> None:
        """Move one current file record in place without starting a new version."""
        file.raw_file_path = path
        file.file_name = file_name
        file.updated_at = utcnow()
        await self.session.flush()

    async def get_by_id(self, file_id: int) -> FileModel | None:
        statement = select(FileModel).where(
            FileModel.id == file_id,
            FileModel.user_id == self.user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_current_by_path(self, path: str) -> FileModel | None:
        statement = select(FileModel).where(
            FileModel.user_id == self.user_id,
            FileModel.raw_file_path == path,
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_current_for_update(self, file_id: int) -> FileModel | None:
        """以資料列鎖定指定檔案，供版本化內容更新在同一個交易內完成。"""
        statement = (
            select(FileModel)
            .where(
                FileModel.id == file_id,
                FileModel.user_id == self.user_id,
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_by_ids(self, file_ids: Sequence[int]) -> list[FileModel]:
        if not file_ids:
            return []
        statement = select(FileModel).where(
            FileModel.user_id == self.user_id,
            FileModel.id.in_(file_ids),
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_current_for_update(
        self,
        *,
        file_ids: Sequence[int],
        folder_paths: Sequence[str],
    ) -> list[FileModel]:
        """鎖定選取的 current files 與所選資料夾底下的所有 current files。"""
        conditions: list[ColumnElement[bool]] = [FileModel.id.in_(file_ids)] if file_ids else []
        conditions.extend(
            FileModel.raw_file_path.startswith(f"{folder.rstrip('/')}/")
            for folder in folder_paths
        )
        if not conditions:
            return []
        statement = (
            select(FileModel)
            .where(
                FileModel.user_id == self.user_id,
                FileModel.is_current.is_(True),
                FileModel.deleted_at.is_(None),
                or_(*conditions),
            )
            .with_for_update()
        )
        return list((await self.session.execute(statement)).scalars().all())

    @staticmethod
    def _directory_prefix(directory: str) -> str:
        return "/" if directory == "/" else f"{directory.rstrip('/')}/"

    async def list_files_in_directory(self, directory: str) -> list[FileModel]:
        prefix = self._directory_prefix(directory)
        statement = select(FileModel).where(
            FileModel.user_id == self.user_id,
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
            FileModel.raw_file_path.startswith(prefix),
            func.strpos(func.substr(FileModel.raw_file_path, len(prefix) + 1), "/") == 0,
        )
        statement = statement.order_by(FileModel.file_name)
        return list((await self.session.execute(statement)).scalars().all())

    async def search_paths(self, prefix: str, query: str, limit: int) -> list[FileModel]:
        scoped_prefix = "/" if prefix == "/" else f"{prefix.rstrip('/')}/"
        statement = (
            select(FileModel)
            .where(
                FileModel.user_id == self.user_id,
                FileModel.is_current.is_(True),
                FileModel.deleted_at.is_(None),
                FileModel.raw_file_path.startswith(scoped_prefix),
                or_(
                    FileModel.raw_file_path.ilike(f"%{query}%"),
                    func.similarity(FileModel.raw_file_path, query) > 0.12,
                ),
            )
            .order_by(
                func.similarity(FileModel.raw_file_path, query).desc(),
                FileModel.updated_at.desc(),
            )
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_updated_in_range(self, start: datetime, end: datetime) -> list[FileModel]:
        statement = (
            select(FileModel)
            .where(
                FileModel.user_id == self.user_id,
                FileModel.is_current.is_(True),
                FileModel.deleted_at.is_(None),
                FileModel.updated_at >= start,
                FileModel.updated_at < end,
            )
            .order_by(FileModel.updated_at)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_current(self) -> int:
        statement = select(func.count(FileModel.id)).where(
            FileModel.user_id == self.user_id,
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def count_current_in_directory(self, directory: str) -> int:
        prefix = self._directory_prefix(directory)
        statement = select(func.count(FileModel.id)).where(
            FileModel.user_id == self.user_id,
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
            FileModel.raw_file_path.startswith(prefix),
            func.strpos(func.substr(FileModel.raw_file_path, len(prefix) + 1), "/") == 0,
        )
        return int((await self.session.execute(statement)).scalar_one())
