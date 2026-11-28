"""The account's own companion catalog: allowed presets and who is active."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.module.companion.dependencies import get_companion_catalog_service
from app.module.companion.schema.companion_admin_schema import CompanionPresetCatalogSchema
from app.module.companion.schema.companion_story_schema import StoryLocaleField
from app.module.companion.service.companion_admin_service import CompanionCatalogService

router = APIRouter(prefix="/companions", tags=["companions"])


@router.get(
    "/presets",
    response_model=CompanionPresetCatalogSchema,
    operation_id="listCompanionPresets",
)
async def list_companion_presets(
    service: Annotated[CompanionCatalogService, Depends(get_companion_catalog_service)],
    locale: Annotated[StoryLocaleField, Query()] = "en",
) -> CompanionPresetCatalogSchema:
    """Presets this account may choose, and how its active companion was resolved."""
    return await service.catalog(locale)
