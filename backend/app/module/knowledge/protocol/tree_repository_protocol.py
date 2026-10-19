"""Persistence contract for the unified tree."""

from collections.abc import Sequence
from typing import Protocol

from app.module.knowledge.model.tree_model import TreeNodeModel


class TreeRepositoryProtocol(Protocol):
    async def add(self, node: TreeNodeModel) -> TreeNodeModel: ...

    async def add_folder_if_absent(self, node: TreeNodeModel) -> TreeNodeModel: ...

    async def flush(self) -> None: ...

    async def get_by_id(self, node_id: int) -> TreeNodeModel | None: ...

    async def get_current_by_path(self, path: str) -> TreeNodeModel | None: ...

    async def get_latest_by_file_id(self, file_id: int) -> TreeNodeModel | None: ...

    async def get_current_children(self, parent_id: int | None) -> list[TreeNodeModel]: ...

    async def list_nodes(
        self,
        *,
        root_path: str,
        root_depth: int,
        max_depth: int,
        include_history: bool,
        limit: int,
    ) -> list[TreeNodeModel]: ...

    async def count_nodes(self, *, include_history: bool) -> int: ...

    async def mark_not_current(
        self,
        node: TreeNodeModel,
        *,
        superseded_by_id: int | None = None,
    ) -> None: ...

    async def update_location(
        self,
        node: TreeNodeModel,
        *,
        parent_id: int | None,
        path: str,
        name: str,
        depth: int,
    ) -> None: ...

    async def mark_deleted(self, node: TreeNodeModel) -> None: ...

    async def delete(self, node: TreeNodeModel) -> None: ...

    async def list_descendants(self, node: TreeNodeModel) -> Sequence[TreeNodeModel]: ...
