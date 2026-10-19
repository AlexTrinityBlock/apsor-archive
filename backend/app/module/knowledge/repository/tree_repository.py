"""SQLAlchemy persistence for the unified tree."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.tree_model import TreeNodeModel
from app.shared.time import utcnow


class TreeRepository:
    """Queries over tree nodes; path validation happens in the service."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, node: TreeNodeModel) -> TreeNodeModel:
        self.session.add(node)
        await self.session.flush()
        return node

    async def add_folder_if_absent(self, node: TreeNodeModel) -> TreeNodeModel:
        """Insert a folder inside a savepoint and return the winning row.

        Concurrent ingestion jobs may race to create the same ancestor folder.
        The partial unique index rejects the loser; rolling back only the
        savepoint keeps the rest of the job transaction usable.
        """
        try:
            async with self.session.begin_nested():
                self.session.add(node)
                await self.session.flush()
            return node
        except IntegrityError:
            existing = await self.get_current_by_path(node.path)
            if existing is None:
                raise
            return existing

    async def flush(self) -> None:
        await self.session.flush()

    async def get_by_id(self, node_id: int) -> TreeNodeModel | None:
        return await self.session.get(TreeNodeModel, node_id)

    async def get_current_by_path(self, path: str) -> TreeNodeModel | None:
        statement = select(TreeNodeModel).where(
            TreeNodeModel.path == path,
            TreeNodeModel.is_current.is_(True),
            TreeNodeModel.deleted_at.is_(None),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_latest_by_file_id(self, file_id: int) -> TreeNodeModel | None:
        """Return the newest node for a file, including unpublished ones."""
        statement = (
            select(TreeNodeModel)
            .where(TreeNodeModel.file_id == file_id)
            .order_by(TreeNodeModel.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_current_children(self, parent_id: int | None) -> list[TreeNodeModel]:
        condition = (
            TreeNodeModel.parent_id.is_(None)
            if parent_id is None
            else TreeNodeModel.parent_id == parent_id
        )
        statement = (
            select(TreeNodeModel)
            .where(
                condition,
                TreeNodeModel.is_current.is_(True),
                TreeNodeModel.deleted_at.is_(None),
            )
            .order_by(TreeNodeModel.kind.desc(), TreeNodeModel.name)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_nodes(
        self,
        *,
        root_path: str,
        root_depth: int,
        max_depth: int,
        include_history: bool,
        limit: int,
    ) -> list[TreeNodeModel]:
        scope = (
            [True]
            if root_path == "/"
            else [
                or_(
                    TreeNodeModel.path == root_path,
                    TreeNodeModel.path.startswith(f"{root_path.rstrip('/')}/"),
                )
            ]
        )
        statement = select(TreeNodeModel).where(
            *scope,
            TreeNodeModel.depth <= root_depth + max_depth,
        )
        if not include_history:
            statement = statement.where(
                TreeNodeModel.is_current.is_(True),
                TreeNodeModel.deleted_at.is_(None),
            )
        statement = statement.order_by(TreeNodeModel.depth, TreeNodeModel.path).limit(limit)
        return list((await self.session.execute(statement)).scalars().all())

    async def count_nodes(self, *, include_history: bool) -> int:
        statement = select(func.count(TreeNodeModel.id))
        if not include_history:
            statement = statement.where(
                TreeNodeModel.is_current.is_(True),
                TreeNodeModel.deleted_at.is_(None),
            )
        return int((await self.session.execute(statement)).scalar_one())

    async def mark_not_current(
        self,
        node: TreeNodeModel,
        *,
        superseded_by_id: int | None = None,
    ) -> None:
        node.is_current = False
        node.superseded_by_id = superseded_by_id
        node.updated_at = utcnow()
        await self.session.flush()

    async def update_location(
        self,
        node: TreeNodeModel,
        *,
        parent_id: int | None,
        path: str,
        name: str,
        depth: int,
    ) -> None:
        """Move one current tree node in place so its identity stays stable."""
        node.parent_id = parent_id
        node.path = path
        node.name = name
        node.depth = depth
        node.updated_at = utcnow()
        await self.session.flush()

    async def mark_deleted(self, node: TreeNodeModel) -> None:
        now = utcnow()
        node.is_current = False
        node.deleted_at = now
        node.updated_at = now
        await self.session.flush()

    async def delete(self, node: TreeNodeModel) -> None:
        """Remove a node created for an ingestion that never published."""
        await self.session.delete(node)
        await self.session.flush()

    async def list_descendants(self, node: TreeNodeModel) -> Sequence[TreeNodeModel]:
        statement = select(TreeNodeModel).where(
            TreeNodeModel.path.startswith(f"{node.path.rstrip('/')}/"),
            TreeNodeModel.deleted_at.is_(None),
        )
        return list((await self.session.execute(statement)).scalars().all())
