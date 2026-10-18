"""Tree reads and the flat payload consumed by the SVG layout engine."""

from app.module.knowledge.domain.path_domain import (
    InvalidPathValueError,
    normalize_directory_path,
)
from app.module.knowledge.exception.domain_error import InvalidPathError, PathNotFoundError
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.tree_repository_protocol import TreeRepositoryProtocol
from app.module.knowledge.schema.file_schema import TreeNodeSchema, TreeSchema
from app.module.knowledge.service.cache_keys import cache_key

MAX_TREE_NODES = 2000


class TreeService:
    """Return a bounded flat tree for visualization and history toggling."""

    def __init__(
        self,
        *,
        tree_repository: TreeRepositoryProtocol,
        cache: CacheProtocol,
        cache_ttl_seconds: int,
    ) -> None:
        self.tree_repository = tree_repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def get_tree(
        self,
        *,
        root: str,
        depth: int,
        include_history: bool,
    ) -> TreeSchema:
        try:
            normalized = normalize_directory_path(root)
        except InvalidPathValueError as exc:
            raise InvalidPathError(str(exc)) from exc
        if depth < 1 or depth > 20:
            raise InvalidPathError("depth must be between 1 and 20.")

        folder = None if normalized == "/" else await self.tree_repository.get_current_by_path(
            normalized
        )
        if normalized != "/" and (folder is None or folder.kind != "folder"):
            raise PathNotFoundError(normalized)

        version = await self.cache.get_version()
        key = cache_key(
            version,
            "tree",
            normalized,
            str(depth),
            str(include_history),
        )
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return TreeSchema.model_validate(cached)

        nodes = await self.tree_repository.list_nodes(
            root_path=normalized,
            root_depth=folder.depth if folder is not None else 0,
            max_depth=depth,
            include_history=include_history,
            limit=MAX_TREE_NODES + 1,
        )
        truncated = len(nodes) > MAX_TREE_NODES
        nodes = nodes[:MAX_TREE_NODES]
        response = TreeSchema(
            root=normalized,
            depth=depth,
            include_history=include_history,
            total=len(nodes),
            truncated=truncated,
            nodes=[
                TreeNodeSchema(
                    id=node.id,
                    parent_id=node.parent_id,
                    path=node.path,
                    name=node.name,
                    kind=node.kind,  # type: ignore[arg-type]
                    file_id=node.file_id,
                    depth=node.depth,
                    is_current=node.is_current,
                    superseded_by_id=node.superseded_by_id,
                    deleted_at=node.deleted_at,
                    update_time=node.updated_at,
                )
                for node in nodes
            ],
        )
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response
