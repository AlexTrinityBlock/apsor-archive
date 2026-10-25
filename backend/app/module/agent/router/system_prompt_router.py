"""HTTP adapter for the custom system prompt."""

from fastapi import APIRouter, Depends

from app.module.agent.dependencies import get_system_prompt_service
from app.module.agent.schema.system_prompt_schema import (
    SystemPromptReadSchema,
    SystemPromptUpdateSchema,
)
from app.module.agent.service.system_prompt_service import SystemPromptService

router = APIRouter(prefix="/settings/system-prompt", tags=["agent"])


@router.get("", response_model=SystemPromptReadSchema, operation_id="getSystemPrompt")
async def get_system_prompt(
    service: SystemPromptService = Depends(get_system_prompt_service),
) -> SystemPromptReadSchema:
    """Return the owner-authored prompt and whether it is active."""
    return await service.get_prompt()


@router.put("", response_model=SystemPromptReadSchema, operation_id="updateSystemPrompt")
async def update_system_prompt(
    payload: SystemPromptUpdateSchema,
    service: SystemPromptService = Depends(get_system_prompt_service),
) -> SystemPromptReadSchema:
    """Replace the prompt used by future conversations."""
    return await service.update_prompt(payload)


@router.post(
    "/reset",
    response_model=SystemPromptReadSchema,
    operation_id="resetSystemPrompt",
)
async def reset_system_prompt(
    service: SystemPromptService = Depends(get_system_prompt_service),
) -> SystemPromptReadSchema:
    """Remove the custom section and return to the built-in prompt."""
    return await service.reset_prompt()
