"""HTTP adapters for editable frequently used prompts.

Every route is authenticated and forwards the acting account to the service.
All roles manage their own list; there is no root-only guard here.
"""

from fastapi import APIRouter, Depends, Response, status

from app.dependency.auth import require_authenticated
from app.module.auth.schema.auth_schema import UserSchema
from app.module.prompt.dependencies import get_frequent_prompt_service
from app.module.prompt.schema.frequent_prompt_schema import (
    FrequentlyUsedPromptCreateSchema,
    FrequentlyUsedPromptReadSchema,
    FrequentlyUsedPromptReorderSchema,
    FrequentlyUsedPromptUpdateSchema,
)
from app.module.prompt.service.frequent_prompt_service import FrequentlyUsedPromptService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(prefix="/settings/frequent-prompts", tags=["prompts"])


@router.get(
    "",
    response_model=ListResponseSchema[FrequentlyUsedPromptReadSchema],
    operation_id="listFrequentlyUsedPrompts",
)
async def list_frequently_used_prompts(
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
    service: FrequentlyUsedPromptService = Depends(get_frequent_prompt_service),  # noqa: B008
) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
    """List the acting user's prompt shortcuts in display order."""
    return await service.list_prompts(user.user_id)


@router.post(
    "",
    response_model=FrequentlyUsedPromptReadSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createFrequentlyUsedPrompt",
)
async def create_frequently_used_prompt(
    payload: FrequentlyUsedPromptCreateSchema,
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
    service: FrequentlyUsedPromptService = Depends(get_frequent_prompt_service),  # noqa: B008
) -> FrequentlyUsedPromptReadSchema:
    """Create a prompt shortcut in the acting user's list."""
    return await service.create_prompt(user.user_id, payload)


@router.post(
    "/reorder",
    response_model=ListResponseSchema[FrequentlyUsedPromptReadSchema],
    operation_id="reorderFrequentlyUsedPrompts",
)
async def reorder_frequently_used_prompts(
    payload: FrequentlyUsedPromptReorderSchema,
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
    service: FrequentlyUsedPromptService = Depends(get_frequent_prompt_service),  # noqa: B008
) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
    """Replace the acting user's complete shortcut order atomically."""
    return await service.reorder_prompts(user.user_id, payload.prompt_ids)


@router.put(
    "/{prompt_id}",
    response_model=FrequentlyUsedPromptReadSchema,
    operation_id="updateFrequentlyUsedPrompt",
)
async def update_frequently_used_prompt(
    prompt_id: int,
    payload: FrequentlyUsedPromptUpdateSchema,
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
    service: FrequentlyUsedPromptService = Depends(get_frequent_prompt_service),  # noqa: B008
) -> FrequentlyUsedPromptReadSchema:
    """Replace the title, text, and order of one prompt owned by the caller."""
    return await service.update_prompt(user.user_id, prompt_id, payload)


@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteFrequentlyUsedPrompt",
)
async def delete_frequently_used_prompt(
    prompt_id: int,
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
    service: FrequentlyUsedPromptService = Depends(get_frequent_prompt_service),  # noqa: B008
) -> Response:
    """Hard-delete one prompt owned by the caller."""
    await service.delete_prompt(user.user_id, prompt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
