"""HTTP adapters for File Library path listings."""

from fastapi import APIRouter, Depends, Query

from app.module.knowledge.dependencies import get_file_service
from app.module.knowledge.schema.file_schema import PathListingSchema
from app.module.knowledge.service.file_service import FileService

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
