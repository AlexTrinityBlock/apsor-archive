"""HTTP adapters for database-backed AI provider settings."""

from fastapi import APIRouter, Depends

from app.module.knowledge.dependencies import get_ai_config_service
from app.module.knowledge.schema.settings_schema import (
    AiProviderUpdateSchema,
    AiSettingsReadSchema,
    AiTestResultSchema,
    EmbeddingReindexSchema,
)
from app.module.knowledge.service.ai_config_service import AiConfigService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ai", response_model=AiSettingsReadSchema, operation_id="getAiSettings")
async def get_ai_settings(
    service: AiConfigService = Depends(get_ai_config_service),
) -> AiSettingsReadSchema:
    """Return both provider slots with masked key hints."""
    return await service.get_settings()


@router.put(
    "/ai/{purpose}",
    response_model=AiSettingsReadSchema,
    operation_id="updateAiProvider",
)
async def update_ai_provider(
    purpose: str,
    payload: AiProviderUpdateSchema,
    service: AiConfigService = Depends(get_ai_config_service),
) -> AiSettingsReadSchema:
    """Update or create one provider configuration and reload it immediately."""
    return await service.update(purpose, payload)


@router.post(
    "/ai/{purpose}/test",
    response_model=AiTestResultSchema,
    operation_id="testAiProvider",
)
async def test_ai_provider(
    purpose: str,
    service: AiConfigService = Depends(get_ai_config_service),
) -> AiTestResultSchema:
    """Make one small provider request and report latency or the error."""
    return await service.test(purpose)


@router.delete(
    "/ai/{purpose}/key",
    response_model=AiSettingsReadSchema,
    operation_id="clearAiProviderKey",
)
async def clear_ai_provider_key(
    purpose: str,
    service: AiConfigService = Depends(get_ai_config_service),
) -> AiSettingsReadSchema:
    """Remove the stored key and reload the provider runtime."""
    return await service.clear_key(purpose)


@router.post(
    "/ai/embedding/reindex",
    response_model=EmbeddingReindexSchema,
    operation_id="reindexEmbeddings",
)
async def reindex_embeddings(
    service: AiConfigService = Depends(get_ai_config_service),
) -> EmbeddingReindexSchema:
    """Re-embed every current chunk with the active embedding provider."""
    return await service.reindex_embeddings()
