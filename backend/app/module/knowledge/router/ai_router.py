"""HTTP adapters for AI answers and status."""

from fastapi import APIRouter, Depends

from app.module.knowledge.dependencies import get_ai_service
from app.module.knowledge.schema.ai_schema import (
    AiStatusSchema,
    AskRequestSchema,
    AskResponseSchema,
)
from app.module.knowledge.service.ai_service import AiService

router = APIRouter(tags=["ai"])


@router.post("/ask", response_model=AskResponseSchema, operation_id="askKnowledge")
async def ask_knowledge(
    payload: AskRequestSchema,
    ai_service: AiService = Depends(get_ai_service),
) -> AskResponseSchema:
    """Answer a question from retrieved sources with explicit citations."""
    return await ai_service.ask(
        question=payload.question,
        result_number=payload.result_number,
    )


@router.get("/ai/status", response_model=AiStatusSchema, operation_id="getAiStatus")
async def get_ai_status(
    ai_service: AiService = Depends(get_ai_service),
) -> AiStatusSchema:
    return ai_service.status()
