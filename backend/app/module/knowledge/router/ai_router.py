"""HTTP adapters for AI configuration status."""

from fastapi import APIRouter, Depends

from app.infrastructure.ai.runtime import AiRuntime
from app.module.knowledge.dependencies import get_ai_runtime, get_ai_service
from app.module.knowledge.schema.ai_schema import AiStatusSchema
from app.module.knowledge.service.ai_service import AiService

router = APIRouter(tags=["ai"])


@router.get("/ai/status", response_model=AiStatusSchema, operation_id="getAiStatus")
async def get_ai_status(
    ai_service: AiService = Depends(get_ai_service),
    ai_runtime: AiRuntime = Depends(get_ai_runtime),
) -> AiStatusSchema:
    status = ai_service.status()
    # The web capability state lives on the runtime clients rather than the
    # knowledge AiService, so enrich the shared status object here.  Provider
    # names are safe to expose; API keys never appear in this schema.
    return status.model_copy(
        update={
            "web_search_provider": ai_runtime.web_search_client.provider,
            "web_search_configured": ai_runtime.web_search_client.configured,
            "web_fetch_provider": ai_runtime.web_fetch_client.provider,
            "web_fetch_configured": ai_runtime.web_fetch_client.configured,
        }
    )
