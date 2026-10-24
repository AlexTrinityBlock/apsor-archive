"""Persistence contract for explicit File Library folders."""

from typing import Protocol

from app.module.knowledge.model.folder_model import FolderModel


class FolderRepositoryProtocol(Protocol):
    async def add(self, folder: FolderModel) -> FolderModel: ...

    async def add_if_absent(self, folder: FolderModel) -> FolderModel: ...

    async def get_by_path(self, path: str) -> FolderModel | None: ...

    async def get_children(self, parent_id: int | None) -> list[FolderModel]: ...

    async def list_descendants(
        self,
        *,
        root_path: str,
        root_depth: int,
        max_depth: int,
        limit: int,
    ) -> list[FolderModel]: ...
