"""HTTP adapters for the unified multi-provider registry."""

from fastapi import APIRouter, Depends, Query

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
    """Delete a provider, renumbering the chain when it was active."""
    return await service.delete(capability, provider_id)


@router.post(
    "/providers/{capability}/{provider_id}/activate",
    response_model=ProviderRegistryReadSchema,
    operation_id="activateProvider",
)
async def activate_provider(
    capability: str,
    provider_id: int,
    priority: int | None = Query(
        default=None,
        ge=0,
        description="Chain position; 0 makes the row primary. Omit to append.",
    ),
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Add or move one row in the chain; omit priority to append it."""
    return await service.activate(capability, provider_id, priority)


@router.post(
    "/providers/{capability}/{provider_id}/deactivate",
    response_model=ProviderRegistryReadSchema,
    operation_id="deactivateProviderRow",
)
async def deactivate_provider_row(
    capability: str,
    provider_id: int,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Remove one row from the chain and close the priority gap."""
    return await service.deactivate_row(capability, provider_id)


@router.post(
    "/providers/{capability}/deactivate",
    response_model=ProviderRegistryReadSchema,
    operation_id="deactivateProvider",
)
async def deactivate_provider(
    capability: str,
    service: ProviderConfigService = Depends(get_provider_config_service),
) -> ProviderRegistryReadSchema:
    """Clear the whole chain; the runtime falls back to environment/default."""
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
