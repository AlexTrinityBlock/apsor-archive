"""HTTP adapters for companion personas and lore (the story editor).

``companion_ref`` is ``preset:<id>`` or ``custom:<id>``. Every route takes a
``locale`` query (``en``, ``zh-TW``, ``zh-CN``); edits are copy-on-write per
locale and reset restores that locale's default. These routes are registered
before the ``/{companion_id}`` routes so the literal ``stories`` segment never
reaches the integer path parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.module.companion.dependencies import get_companion_story_service
from app.module.companion.schema.companion_story_schema import (
    CompanionLoreCreateSchema,
    CompanionLoreSchema,
    CompanionLoreUpdateSchema,
    CompanionPersonaSchema,
    CompanionPersonaUpdateSchema,
    StoryLocaleField,
)
from app.module.companion.service.companion_story_service import CompanionStoryService

router = APIRouter(prefix="/companions/stories", tags=["companions"])

Service = Annotated[CompanionStoryService, Depends(get_companion_story_service)]
Locale = Annotated[StoryLocaleField, Query(description="Story language to read or edit.")]
CompanionRef = Annotated[
    str,
    Path(max_length=64, description="preset:<id> or custom:<id>"),
]
FragmentId = Annotated[str, Path(max_length=64)]


@router.get(
    "/{companion_ref}/persona",
    response_model=CompanionPersonaSchema,
    operation_id="getCompanionPersona",
)
async def get_companion_persona(
    companion_ref: CompanionRef,
    service: Service,
    locale: Locale = "en",
) -> CompanionPersonaSchema:
    """Return the persona in effect for this account and locale."""
    return await service.get_persona(companion_ref, locale)


@router.put(
    "/{companion_ref}/persona",
    response_model=CompanionPersonaSchema,
    operation_id="updateCompanionPersona",
)
async def update_companion_persona(
    companion_ref: CompanionRef,
    payload: CompanionPersonaUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionPersonaSchema:
    """Replace this account's persona; it applies to new conversations."""
    return await service.update_persona(companion_ref, locale, payload)


@router.delete(
    "/{companion_ref}/persona",
    response_model=CompanionPersonaSchema,
    operation_id="resetCompanionPersona",
)
async def reset_companion_persona(
    companion_ref: CompanionRef,
    service: Service,
    locale: Locale = "en",
) -> CompanionPersonaSchema:
    """Drop this locale's persona override and return the default."""
    return await service.reset_persona(companion_ref, locale)


@router.get(
    "/{companion_ref}/lore",
    response_model=CompanionLoreSchema,
    operation_id="listCompanionLore",
)
async def list_companion_lore(
    companion_ref: CompanionRef,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreSchema:
    """Return the lore the account may see (its own and what it has heard)."""
    return await service.list_lore(companion_ref, locale)


@router.post(
    "/{companion_ref}/lore",
    response_model=CompanionLoreSchema,
    status_code=201,
    operation_id="createCompanionLore",
)
async def create_companion_lore(
    companion_ref: CompanionRef,
    payload: CompanionLoreCreateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreSchema:
    """Add a fragment (copying this locale's defaults on the first edit)."""
    return await service.create_lore(companion_ref, locale, payload)


@router.post(
    "/{companion_ref}/lore/reset",
    response_model=CompanionLoreSchema,
    operation_id="resetCompanionLore",
)
async def reset_companion_lore(
    companion_ref: CompanionRef,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreSchema:
    """Discard this locale's lore copy and return the default fragments."""
    return await service.reset_lore(companion_ref, locale)


@router.patch(
    "/{companion_ref}/lore/{fragment_id}",
    response_model=CompanionLoreSchema,
    operation_id="updateCompanionLore",
)
async def update_companion_lore(
    companion_ref: CompanionRef,
    fragment_id: FragmentId,
    payload: CompanionLoreUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreSchema:
    """Edit one fragment's text, themes, weight, or position."""
    return await service.update_lore(companion_ref, locale, fragment_id, payload)


@router.delete(
    "/{companion_ref}/lore/{fragment_id}",
    response_model=CompanionLoreSchema,
    operation_id="deleteCompanionLore",
)
async def delete_companion_lore(
    companion_ref: CompanionRef,
    fragment_id: FragmentId,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreSchema:
    """Remove one fragment from this account's copy."""
    return await service.delete_lore(companion_ref, locale, fragment_id)


__all__ = ["router"]
