"""SQLAlchemy persistence for File Library folders.

Folder paths are unique per owner. Every query carries the repository owner so a
path lookup can never resolve to another account's folder, even without RLS.
"""

from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.folder_model import FolderModel


class FolderRepository:
    """Queries over one owner's explicit folder rows."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def add(self, folder: FolderModel) -> FolderModel:
        folder.user_id = self.user_id
        self.session.add(folder)
        await self.session.flush()
        return folder

    async def add_if_absent(self, folder: FolderModel) -> FolderModel:
        """Insert a folder inside a savepoint and return the winning row.

        Concurrent ingestion jobs may race to create the same ancestor folder.
        The unique index rejects the loser; rolling back only the savepoint
        keeps the rest of the job transaction usable.
        """
        folder.user_id = self.user_id
        try:
            async with self.session.begin_nested():
                self.session.add(folder)
                await self.session.flush()
            return folder
        except IntegrityError:
            existing = await self.get_by_path(folder.path)
            if existing is None:
                raise
            return existing

    async def get_by_path(self, path: str) -> FolderModel | None:
        statement = select(FolderModel).where(
            FolderModel.user_id == self.user_id,
            FolderModel.path == path,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_children(self, parent_id: int | None) -> list[FolderModel]:
        condition = (
            FolderModel.parent_id.is_(None)
            if parent_id is None
            else FolderModel.parent_id == parent_id
        )
        statement = (
            select(FolderModel)
            .where(
                FolderModel.user_id == self.user_id,
                condition,
            )
            .order_by(FolderModel.name)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_for_update(self, paths: Sequence[str]) -> list[FolderModel]:
        """Lock the selected folders and all of their descendants."""
        if not paths:
            return []
        conditions = [
            clause
            for path in paths
            for clause in (
                FolderModel.path == path,
                FolderModel.path.startswith(f"{path.rstrip('/')}/"),
            )
        ]
        statement = (
            select(FolderModel)
            .where(
                FolderModel.user_id == self.user_id,
                or_(*conditions),
            )
            .with_for_update()
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def delete_many(self, folders: Sequence[FolderModel]) -> None:
        """Remove a whole folder subtree with one DELETE, avoiding parent/child ordering issues."""
        if not folders:
            return
        await self.session.execute(
            delete(FolderModel).where(
                FolderModel.user_id == self.user_id,
                FolderModel.id.in_([folder.id for folder in folders]),
            )
        )

    async def list_descendants(
        self,
        *,
        root_path: str,
        root_depth: int,
        max_depth: int,
        limit: int,
    ) -> list[FolderModel]:
        """List folders at or below ``root_path`` within ``max_depth``."""
        scope = (
            [True]
            if root_path == "/"
            else [
                or_(
                    FolderModel.path == root_path,
                    FolderModel.path.startswith(f"{root_path.rstrip('/')}/"),
                )
            ]
        )
        statement = (
            select(FolderModel)
            .where(
                FolderModel.user_id == self.user_id,
                *scope,
                FolderModel.depth <= root_depth + max_depth,
            )
            .order_by(FolderModel.depth, FolderModel.path)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())
