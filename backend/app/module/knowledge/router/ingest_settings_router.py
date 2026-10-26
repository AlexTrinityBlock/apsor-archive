"""HTTP adapters for database-backed ingestion runtime settings."""

from fastapi import APIRouter, Depends

from app.dependency.auth import require_root
from app.module.knowledge.dependencies import get_ingest_settings_service
from app.module.knowledge.schema.ingest_settings_schema import (
    IngestSettingsReadSchema,
    IngestSettingsUpdateSchema,
)
from app.module.knowledge.service.ingest_settings_service import IngestSettingsService

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_root)],
)


@router.get(
    "/ingest",
    response_model=IngestSettingsReadSchema,
    operation_id="getIngestSettings",
)
async def get_ingest_settings(
    service: IngestSettingsService = Depends(get_ingest_settings_service),
) -> IngestSettingsReadSchema:
    """Return the effective worker settings and the defaults."""
    return await service.get_settings()


@router.put(
    "/ingest",
    response_model=IngestSettingsReadSchema,
    operation_id="updateIngestSettings",
)
async def update_ingest_settings(
    payload: IngestSettingsUpdateSchema,
    service: IngestSettingsService = Depends(get_ingest_settings_service),
) -> IngestSettingsReadSchema:
    """Replace every worker setting with one validated snapshot."""
    return await service.update_settings(payload)


@router.post(
    "/ingest/reset",
    response_model=IngestSettingsReadSchema,
    operation_id="resetIngestSettings",
)
async def reset_ingest_settings(
    service: IngestSettingsService = Depends(get_ingest_settings_service),
) -> IngestSettingsReadSchema:
    """Restore and persist the environment-seeded defaults."""
    return await service.reset_settings()


__all__ = ["router"]
