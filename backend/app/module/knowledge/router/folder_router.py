"""HTTP adapters for folder creation, rename, move, and copy."""

from fastapi import APIRouter, Depends, status

from app.module.knowledge.dependencies import get_file_service
from app.module.knowledge.schema.file_schema import (
    DirectorySchema,
    FolderCopySchema,
    FolderCreateSchema,
    FolderMoveSchema,
    FolderMutationSchema,
    FolderRenameSchema,
)
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


@router.post(
    "/rename",
    response_model=FolderMutationSchema,
    status_code=status.HTTP_200_OK,
    operation_id="renameFolder",
)
async def rename_folder(
    payload: FolderRenameSchema,
    file_service: FileService = Depends(get_file_service),
) -> FolderMutationSchema:
    """Rename one folder in place; the parent folder never changes."""
    return await file_service.rename_folder(payload.path, new_name=payload.new_name)


@router.post(
    "/move",
    response_model=FolderMutationSchema,
    status_code=status.HTTP_200_OK,
    operation_id="moveFolder",
)
async def move_folder(
    payload: FolderMoveSchema,
    file_service: FileService = Depends(get_file_service),
) -> FolderMutationSchema:
    """Move one folder subtree to a complete destination path."""
    return await file_service.move_folder(payload.path, target_path=payload.target_path)


@router.post(
    "/copy",
    response_model=FolderMutationSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="copyFolder",
)
async def copy_folder(
    payload: FolderCopySchema,
    file_service: FileService = Depends(get_file_service),
) -> FolderMutationSchema:
    """Copy one folder subtree, cloning its chunks without re-embedding."""
    return await file_service.copy_folder(payload.path, target_path=payload.target_path)
