"""HTTP adapters for ordered, globally managed system prompt sections.

Reads and writes use the system-scoped repository; this router is root-only
because prompt sections are global deployment configuration. Normal accounts see
the frozen prompt of their own conversation, never a write surface.
"""

from fastapi import APIRouter, Depends, Response, status

from app.dependency.auth import require_root
from app.module.agent.dependencies import get_system_prompt_admin_service
from app.module.agent.schema.system_prompt_schema import (
    SystemPromptReorderSchema,
    SystemPromptSectionCreateSchema,
    SystemPromptSectionReadSchema,
    SystemPromptSectionUpdateSchema,
)
from app.module.agent.service.system_prompt_service import SystemPromptService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(
    prefix="/settings/system-prompt",
    tags=["agent"],
    dependencies=[Depends(require_root)],
)


# Route order matters: ``/order`` and ``/reset`` must be declared before
# ``/{section_id}`` or Starlette matches the fixed strings as a path parameter
# and returns a 422 while trying to parse them as integers.


@router.get(
    "",
    response_model=ListResponseSchema[SystemPromptSectionReadSchema],
    operation_id="listSystemPromptSections",
)
async def list_system_prompt_sections(
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    """List every section in display order."""
    return await service.list_sections()


@router.post(
    "",
    response_model=ListResponseSchema[SystemPromptSectionReadSchema],
    status_code=status.HTTP_201_CREATED,
    operation_id="createSystemPromptSection",
)
async def create_system_prompt_section(
    payload: SystemPromptSectionCreateSchema,
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    """Create one section and return the updated list."""
    return await service.create_section(payload)


@router.put(
    "/order",
    response_model=ListResponseSchema[SystemPromptSectionReadSchema],
    operation_id="reorderSystemPromptSections",
)
async def reorder_system_prompt_sections(
    payload: SystemPromptReorderSchema,
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    """Replace the complete section order."""
    return await service.reorder_sections(payload.section_ids)


@router.post(
    "/reset",
    response_model=ListResponseSchema[SystemPromptSectionReadSchema],
    operation_id="resetSystemPromptSections",
)
async def reset_system_prompt_sections(
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    """Replace every section with the four seeded defaults."""
    return await service.reset_sections()


@router.put(
    "/{section_id}",
    response_model=ListResponseSchema[SystemPromptSectionReadSchema],
    operation_id="updateSystemPromptSection",
)
async def update_system_prompt_section(
    section_id: int,
    payload: SystemPromptSectionUpdateSchema,
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    """Replace one section and return the updated list."""
    return await service.update_section(section_id, payload)


@router.delete(
    "/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSystemPromptSection",
)
async def delete_system_prompt_section(
    section_id: int,
    service: SystemPromptService = Depends(get_system_prompt_admin_service),
) -> Response:
    """Hard-delete one section."""
    await service.delete_section(section_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
