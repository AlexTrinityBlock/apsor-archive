"""HTTP adapters for the unified multi-provider registry."""

from fastapi import APIRouter, Depends

from app.dependency.auth import require_root
from app.module.knowledge.dependencies import get_provider_config_service
from app.module.knowledge.schema.provider_config_schema import (
    ProviderCreateSchema,
    ProviderRegistryReadSchema,
    ProviderTestResultSchema,
    ProviderUpdateSchema,
)
from app.module.knowledge.schema.settings_schema import EmbeddingReindexSchema
from app.module.knowledge.service.provider_config_service import ProviderConfigService

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_root)],
)


@router.get(
    "/providers",
    response_model=ProviderRegistryReadSchema,
    operation_id="getProviderRegistry",
)
async def get_provider_registry(
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Return all four capability groups with active and saved providers."""
    return await service.get_registry()


@router.post(
    "/providers/{capability}",
    response_model=ProviderRegistryReadSchema,
    operation_id="createProvider",
)
async def create_provider(
    capability: str,
    payload: ProviderCreateSchema,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Create one provider row and optionally activate it immediately."""
    return await service.create(capability, payload)


@router.put(
    "/providers/{capability}/{provider_id}",
    response_model=ProviderRegistryReadSchema,
    operation_id="updateProvider",
)
async def update_provider(
    capability: str,
    provider_id: int,
    payload: ProviderUpdateSchema,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Replace one provider row without ever returning its plaintext key."""
    return await service.update(capability, provider_id, payload)


@router.delete(
    "/providers/{capability}/{provider_id}",
    response_model=ProviderRegistryReadSchema,
    operation_id="deleteProvider",
)
async def delete_provider(
    capability: str,
    provider_id: int,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Delete a provider, deactivating it first when it is the active row."""
    return await service.delete(capability, provider_id)


@router.post(
    "/providers/{capability}/{provider_id}/activate",
    response_model=ProviderRegistryReadSchema,
    operation_id="activateProvider",
)
async def activate_provider(
    capability: str,
    provider_id: int,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Make one row the only active provider for its capability."""
    return await service.activate(capability, provider_id)


@router.post(
    "/providers/{capability}/deactivate",
    response_model=ProviderRegistryReadSchema,
    operation_id="deactivateProvider",
)
async def deactivate_provider(
    capability: str,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Clear the active row; the runtime falls back to environment/default."""
    return await service.deactivate(capability)


@router.post(
    "/providers/{capability}/{provider_id}/test",
    response_model=ProviderTestResultSchema,
    operation_id="testProvider",
)
async def test_provider(
    capability: str,
    provider_id: int,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderTestResultSchema:
    """Make one small provider request and report latency or the error."""
    return await service.test(capability, provider_id)


@router.post(
    "/providers/embedding/reindex",
    response_model=EmbeddingReindexSchema,
    operation_id="reindexEmbeddings",
)
async def reindex_embeddings(
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> EmbeddingReindexSchema:
    """Re-embed every current chunk with the active embedding provider."""
    return await service.reindex_embeddings()


__all__ = ["router"]
