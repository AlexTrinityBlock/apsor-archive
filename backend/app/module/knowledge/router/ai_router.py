"""HTTP adapters for AI configuration status."""

from fastapi import APIRouter, Depends

from app.module.knowledge.dependencies import get_ai_service
from app.module.knowledge.schema.ai_schema import AiStatusSchema
from app.module.knowledge.service.ai_service import AiService

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=AiStatusSchema, operation_id="getAiStatus")
async def get_ai_status(
    ai_service: AiService = Depends(get_ai_service),
) -> AiStatusSchema:
    return ai_service.status()
