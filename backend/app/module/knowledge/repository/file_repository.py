"""SQLAlchemy persistence for files."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.file_model import FileModel
from app.shared.time import utcnow


class FileRepository:
    """Queries over the file table; no business decisions live here."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, file: FileModel) -> FileModel:
        self.session.add(file)
        await self.session.flush()
        return file

    async def mark_not_current(self, file: FileModel) -> None:
        file.is_current = False
        file.updated_at = utcnow()
        await self.session.flush()

    async def get_by_id(self, file_id: int) -> FileModel | None:
        return await self.session.get(FileModel, file_id)

    async def get_current_by_path(self, path: str) -> FileModel | None:
        statement = select(FileModel).where(
            FileModel.raw_file_path == path,
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_by_ids(self, file_ids: Sequence[int]) -> list[FileModel]:
        if not file_ids:
            return []
        statement = select(FileModel).where(FileModel.id.in_(file_ids))
        return list((await self.session.execute(statement)).scalars().all())

    @staticmethod
    def _directory_prefix(directory: str) -> str:
        return "/" if directory == "/" else f"{directory.rstrip('/')}/"

    async def list_files_in_directory(self, directory: str) -> list[FileModel]:
        prefix = self._directory_prefix(directory)
        statement = select(FileModel).where(
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
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def count_current_in_directory(self, directory: str) -> int:
        prefix = self._directory_prefix(directory)
        statement = select(func.count(FileModel.id)).where(
            FileModel.is_current.is_(True),
            FileModel.deleted_at.is_(None),
            FileModel.raw_file_path.startswith(prefix),
            func.strpos(func.substr(FileModel.raw_file_path, len(prefix) + 1), "/") == 0,
        )
        return int((await self.session.execute(statement)).scalar_one())
