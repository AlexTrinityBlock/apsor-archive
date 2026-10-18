"""HTTP adapters for folder creation."""

from fastapi import APIRouter, Depends, status

from app.module.knowledge.dependencies import get_file_service
from app.module.knowledge.schema.file_schema import DirectorySchema, FolderCreateSchema
from app.module.knowledge.service.file_service import FileService

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post(
    "",
    response_model=DirectorySchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createFolder",
)
async def create_folder(
    payload: FolderCreateSchema,
    file_service: FileService = Depends(get_file_service),
) -> DirectorySchema:
    """Create a folder and its missing ancestors; return 201 on every success.

    Returning the existing folder with the same 201 keeps the API idempotent
    for clients without a second status branch.
    """
    return await file_service.create_folder(payload.path)
