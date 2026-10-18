"""HTTP adapters for path listings and the knowledge tree."""

from fastapi import APIRouter, Depends, Query

from app.module.knowledge.dependencies import get_file_service, get_tree_service
from app.module.knowledge.schema.file_schema import PathListingSchema, TreeSchema
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.tree_service import TreeService

router = APIRouter(tags=["tree"])


@router.get("/paths", response_model=PathListingSchema, operation_id="readPath")
async def read_path(
    path: str = Query(default="/", min_length=1, max_length=1024),
    path_depth: int = Query(default=1, ge=1, le=10),
    fuzzy_search: str | None = Query(default=None, max_length=120),
    file_service: FileService = Depends(get_file_service),
) -> PathListingSchema:
    """List a directory or fuzzy-search file paths (the read_path tool)."""
    return await file_service.list_path(
        path=path,
        path_depth=path_depth,
        fuzzy_search=fuzzy_search,
    )


@router.get("/tree", response_model=TreeSchema, operation_id="getTree")
async def get_tree(
    root: str = Query(default="/", min_length=1, max_length=1024),
    depth: int = Query(default=20, ge=1, le=20),
    include_history: bool = False,
    tree_service: TreeService = Depends(get_tree_service),
) -> TreeSchema:
    """Return a flat tree; the frontend performs the SVG layout."""
    return await tree_service.get_tree(
        root=root,
        depth=depth,
        include_history=include_history,
    )
