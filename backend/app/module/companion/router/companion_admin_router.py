"""Root-only HTTP surface for companions, the world canon, and per-account stories.

Every route depends on ``get_companion_admin_service``: ``require_root`` plus the
companion admin scope on the request transaction. Listing generated stories never
returns their text; ``getCompanionGeneratedStoryAdmin`` does and is logged.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.module.companion.dependencies import get_companion_admin_service
from app.module.companion.schema.companion_admin_schema import (
    CompanionAccessLogSchema,
    CompanionBondAdminUpdateSchema,
    CompanionCanonEntitySchema,
    CompanionCanonEntityUpsertSchema,
    CompanionConfigAdminSchema,
    CompanionConfigAdminUpdateSchema,
    CompanionFragmentProgressUpdateSchema,
    CompanionGeneratedStorySchema,
    CompanionGeneratedStorySummarySchema,
    CompanionGeneratedStoryUpdateSchema,
    CompanionLoreItemAdminCreateSchema,
    CompanionLoreItemAdminSchema,
    CompanionLoreItemAdminUpdateSchema,
    CompanionLoreOverrideSchema,
    CompanionLoreOverrideUpsertSchema,
    CompanionPersonaOverrideSchema,
    CompanionPersonaOverrideUpdateSchema,
    CompanionPolicyAdminSchema,
    CompanionPolicyAdminUpdateSchema,
    CompanionPresetAdminSchema,
    CompanionPresetAdminUpdateSchema,
    CompanionPresetTextAdminSchema,
    CompanionPresetTextAdminUpdateSchema,
    CompanionProgressResetSchema,
    CompanionSeedApplySchema,
    CompanionSeedStatusSchema,
    CompanionStoryGenerateSchema,
    CompanionStoryJobSchema,
    CompanionTemplateAdminSchema,
    CompanionTemplateAdminUpdateSchema,
    CompanionTemplatePreviewRequestSchema,
    CompanionTemplatePreviewSchema,
    CompanionUserAdminSchema,
    CompanionUserConfigAdminSchema,
    CompanionUserConfigAdminUpdateSchema,
    CompanionUserFragmentsSchema,
    CompanionUserSummarySchema,
    CompanionWorldDocRevisionSchema,
    CompanionWorldDocSchema,
    CompanionWorldDocSummarySchema,
    CompanionWorldDocUpdateSchema,
    LoreWeightField,
    OriginField,
    StoryLocaleField,
)
from app.module.companion.service.companion_admin_service import CompanionAdminService

router = APIRouter(prefix="/admin/companions", tags=["companion-admin"])

Service = Annotated[CompanionAdminService, Depends(get_companion_admin_service)]
Locale = Annotated[StoryLocaleField, Query(description="Content language.")]
PresetId = Annotated[str, Path(max_length=48)]
UserId = Annotated[int, Path(ge=1)]
CompanionRef = Annotated[str, Path(max_length=64, description="preset:<id> or custom:<id>")]
DocKey = Annotated[str, Path(max_length=64)]
TemplateKey = Annotated[str, Path(max_length=48)]
FragmentKey = Annotated[str, Path(max_length=64)]


# --- presets -----------------------------------------------------------------------


@router.get(
    "/presets",
    response_model=list[CompanionPresetAdminSchema],
    operation_id="listCompanionPresetsAdmin",
)
async def list_presets(service: Service) -> list[CompanionPresetAdminSchema]:
    """List every preset librarian, including ones only in the seed files."""
    return await service.list_presets()


@router.patch(
    "/presets/{preset_id}",
    response_model=CompanionPresetAdminSchema,
    operation_id="updateCompanionPresetAdmin",
)
async def update_preset(
    preset_id: PresetId, payload: CompanionPresetAdminUpdateSchema, service: Service
) -> CompanionPresetAdminSchema:
    """Enable, reorder, or make a preset the global default."""
    return await service.update_preset(preset_id, payload)


@router.get(
    "/presets/{preset_id}/text",
    response_model=CompanionPresetTextAdminSchema,
    operation_id="getCompanionPresetTextAdmin",
)
async def get_preset_text(
    preset_id: PresetId, service: Service, locale: Locale = "en"
) -> CompanionPresetTextAdminSchema:
    """Return a preset's name and persona in one locale."""
    return await service.get_preset_text(preset_id, locale)


@router.put(
    "/presets/{preset_id}/text",
    response_model=CompanionPresetTextAdminSchema,
    operation_id="updateCompanionPresetTextAdmin",
)
async def update_preset_text(
    preset_id: PresetId,
    payload: CompanionPresetTextAdminUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionPresetTextAdminSchema:
    """Replace a preset's name or persona in one locale."""
    return await service.update_preset_text(preset_id, locale, payload)


@router.post(
    "/presets/{preset_id}/text/reset",
    response_model=CompanionPresetTextAdminSchema,
    operation_id="resetCompanionPresetTextAdmin",
)
async def reset_preset_text(
    preset_id: PresetId, service: Service, locale: Locale = "en"
) -> CompanionPresetTextAdminSchema:
    """Restore a preset's shipped name and persona."""
    return await service.reset_preset_text(preset_id, locale)


# --- lore ---------------------------------------------------------------------------


@router.get(
    "/lore",
    response_model=list[CompanionLoreItemAdminSchema],
    operation_id="listCompanionLoreAdmin",
)
async def list_lore(
    service: Service,
    locale: Locale = "en",
    preset: Annotated[str | None, Query(max_length=48)] = None,
    weight: LoreWeightField | None = None,
    theme: Annotated[str | None, Query(max_length=40)] = None,
    ref: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    origin: OriginField | None = None,
    upstream_changed: bool | None = None,
) -> list[CompanionLoreItemAdminSchema]:
    """Search the global lore; seed-only items have id 0 until first edited."""
    return await service.list_lore(
        preset_id=preset,
        locale=locale,
        weight=weight,
        theme=theme,
        ref=ref,
        query=q,
        origin=origin,
        upstream_changed=upstream_changed,
    )


@router.post(
    "/lore",
    response_model=CompanionLoreItemAdminSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCompanionLoreAdmin",
)
async def create_lore(
    payload: CompanionLoreItemAdminCreateSchema, service: Service
) -> CompanionLoreItemAdminSchema:
    """Add a lore item to a preset."""
    return await service.create_lore(payload)


@router.patch(
    "/lore/{preset_id}/{fragment_key}",
    response_model=CompanionLoreItemAdminSchema,
    operation_id="updateCompanionLoreAdmin",
)
async def update_lore(
    preset_id: PresetId,
    fragment_key: FragmentKey,
    payload: CompanionLoreItemAdminUpdateSchema,
    service: Service,
) -> CompanionLoreItemAdminSchema:
    """Edit a lore item (a seed-only item is copied into the database first)."""
    item_id = await service.resolve_lore_id(preset_id, fragment_key)
    return await service.update_lore(item_id, payload)


@router.post(
    "/lore/{preset_id}/{fragment_key}/retire",
    response_model=CompanionLoreItemAdminSchema,
    operation_id="retireCompanionLoreAdmin",
)
async def retire_lore(
    preset_id: PresetId, fragment_key: FragmentKey, service: Service
) -> CompanionLoreItemAdminSchema:
    """Retire a lore item, or bring a retired one back."""
    item_id = await service.resolve_lore_id(preset_id, fragment_key)
    return await service.retire_lore(item_id)


@router.post(
    "/lore/{preset_id}/{fragment_key}/reset",
    response_model=CompanionLoreItemAdminSchema,
    operation_id="resetCompanionLoreAdmin",
)
async def reset_lore(
    preset_id: PresetId, fragment_key: FragmentKey, service: Service
) -> CompanionLoreItemAdminSchema:
    """Restore a shipped lore item's text and metadata."""
    item_id = await service.resolve_lore_id(preset_id, fragment_key)
    return await service.reset_lore(item_id)


# --- world documents and canon ---------------------------------------------------------


@router.get(
    "/world-docs",
    response_model=list[CompanionWorldDocSummarySchema],
    operation_id="listCompanionWorldDocsAdmin",
)
async def list_world_docs(service: Service) -> list[CompanionWorldDocSummarySchema]:
    """List the world bible, glossary, overview, term tables, and character files."""
    return await service.list_world_docs()


@router.get(
    "/world-docs/{doc_key}",
    response_model=CompanionWorldDocSchema,
    operation_id="getCompanionWorldDocAdmin",
)
async def get_world_doc(
    doc_key: DocKey, service: Service, locale: Locale = "en"
) -> CompanionWorldDocSchema:
    """Return one world document with its markdown body."""
    doc = await service.get_world_doc(doc_key, locale)
    assert doc is not None
    return doc


@router.put(
    "/world-docs/{doc_key}",
    response_model=CompanionWorldDocSchema,
    operation_id="updateCompanionWorldDocAdmin",
)
async def update_world_doc(
    doc_key: DocKey,
    payload: CompanionWorldDocUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionWorldDocSchema:
    """Replace a world document; the previous version is kept as a revision."""
    return await service.update_world_doc(doc_key, locale, payload)


@router.get(
    "/world-docs/{doc_key}/revisions",
    response_model=list[CompanionWorldDocRevisionSchema],
    operation_id="listCompanionWorldDocRevisionsAdmin",
)
async def list_world_doc_revisions(
    doc_key: DocKey, service: Service, locale: Locale = "en"
) -> list[CompanionWorldDocRevisionSchema]:
    """List a document's previous versions, newest first."""
    return await service.list_doc_revisions(doc_key, locale)


@router.post(
    "/world-docs/{doc_key}/reset",
    response_model=CompanionWorldDocSchema,
    operation_id="resetCompanionWorldDocAdmin",
)
async def reset_world_doc(
    doc_key: DocKey, service: Service, locale: Locale = "en"
) -> CompanionWorldDocSchema:
    """Restore the shipped version of a world document."""
    return await service.reset_world_doc(doc_key, locale)


@router.get(
    "/canon",
    response_model=list[CompanionCanonEntitySchema],
    operation_id="listCompanionCanonAdmin",
)
async def list_canon(service: Service, locale: Locale = "en") -> list[CompanionCanonEntitySchema]:
    """List the canon entities in one locale."""
    return await service.list_canon(locale)


@router.put(
    "/canon",
    response_model=CompanionCanonEntitySchema,
    operation_id="upsertCompanionCanonEntityAdmin",
)
async def upsert_canon(
    payload: CompanionCanonEntityUpsertSchema, service: Service
) -> CompanionCanonEntitySchema:
    """Create or replace one canon entity."""
    return await service.upsert_canon(payload)


# --- config, templates, seed -----------------------------------------------------------------


@router.get(
    "/config",
    response_model=CompanionConfigAdminSchema,
    operation_id="getCompanionConfigAdmin",
)
async def get_config(service: Service) -> CompanionConfigAdminSchema:
    """Return every story tunable with its shipped default."""
    return await service.get_config()


@router.patch(
    "/config",
    response_model=CompanionConfigAdminSchema,
    operation_id="updateCompanionConfigAdmin",
)
async def update_config(
    payload: CompanionConfigAdminUpdateSchema, service: Service
) -> CompanionConfigAdminSchema:
    """Change one or more global story tunables."""
    return await service.update_config(payload)


@router.post(
    "/config/reset",
    response_model=CompanionConfigAdminSchema,
    operation_id="resetCompanionConfigAdmin",
)
async def reset_config(service: Service) -> CompanionConfigAdminSchema:
    """Restore every global tunable to its shipped default."""
    return await service.reset_config()


@router.get(
    "/templates",
    response_model=list[CompanionTemplateAdminSchema],
    operation_id="listCompanionTemplatesAdmin",
)
async def list_templates(service: Service) -> list[CompanionTemplateAdminSchema]:
    """List guidance strings and prompt templates."""
    return await service.list_templates()


@router.put(
    "/templates/{template_key}",
    response_model=CompanionTemplateAdminSchema,
    operation_id="updateCompanionTemplateAdmin",
)
async def update_template(
    template_key: TemplateKey,
    payload: CompanionTemplateAdminUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionTemplateAdminSchema:
    """Replace a template body; required placeholders must stay."""
    return await service.update_template(template_key, locale, payload)


@router.post(
    "/templates/{template_key}/reset",
    response_model=CompanionTemplateAdminSchema,
    operation_id="resetCompanionTemplateAdmin",
)
async def reset_template(
    template_key: TemplateKey, service: Service, locale: Locale = "en"
) -> CompanionTemplateAdminSchema:
    """Restore a template's shipped body."""
    return await service.reset_template(template_key, locale)


@router.post(
    "/templates/preview",
    response_model=CompanionTemplatePreviewSchema,
    operation_id="previewCompanionTemplateAdmin",
)
async def preview_template(
    payload: CompanionTemplatePreviewRequestSchema, service: Service
) -> CompanionTemplatePreviewSchema:
    """Render a template against a fictional sample (never a real archive)."""
    return await service.preview_template(payload)


@router.get(
    "/seed",
    response_model=CompanionSeedStatusSchema,
    operation_id="getCompanionSeedStatusAdmin",
)
async def get_seed_status(service: Service) -> CompanionSeedStatusSchema:
    """Report whether the shipped seed has been applied and what drifted."""
    return await service.seed_status()


@router.post(
    "/seed/apply",
    response_model=CompanionSeedStatusSchema,
    operation_id="applyCompanionSeedAdmin",
)
async def apply_seed(
    payload: CompanionSeedApplySchema, service: Service
) -> CompanionSeedStatusSchema:
    """Re-apply the shipped seed; ``force_keys`` overwrite admin edits."""
    return await service.apply_seed(payload)


# --- per account ----------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=list[CompanionUserSummarySchema],
    operation_id="listCompanionUserSummariesAdmin",
)
async def list_users(service: Service) -> list[CompanionUserSummarySchema]:
    """Every account with its companion activity."""
    return await service.list_user_summaries()


@router.get(
    "/users/{user_id}",
    response_model=CompanionUserAdminSchema,
    operation_id="getCompanionUserAdmin",
)
async def get_user(user_id: UserId, service: Service) -> CompanionUserAdminSchema:
    """One account's policy and bonds with every companion."""
    return await service.get_user(user_id)


@router.get(
    "/users/{user_id}/policy",
    response_model=CompanionPolicyAdminSchema,
    operation_id="getCompanionAccountPolicyAdmin",
)
async def get_policy(user_id: UserId, service: Service) -> CompanionPolicyAdminSchema:
    """Root's companion policy for one account and the resolved companion."""
    return await service.get_policy(user_id)


@router.put(
    "/users/{user_id}/policy",
    response_model=CompanionPolicyAdminSchema,
    operation_id="updateCompanionAccountPolicyAdmin",
)
async def update_policy(
    user_id: UserId, payload: CompanionPolicyAdminUpdateSchema, service: Service
) -> CompanionPolicyAdminSchema:
    """Set the default, allowed set, and optional pin for one account."""
    return await service.update_policy(user_id, payload)


@router.get(
    "/users/{user_id}/config",
    response_model=CompanionUserConfigAdminSchema,
    operation_id="getCompanionUserConfigAdmin",
)
async def get_user_config(user_id: UserId, service: Service) -> CompanionUserConfigAdminSchema:
    """Per-account tunables (null inherits the global value)."""
    return await service.get_user_config(user_id)


@router.patch(
    "/users/{user_id}/config",
    response_model=CompanionUserConfigAdminSchema,
    operation_id="updateCompanionUserConfigAdmin",
)
async def update_user_config(
    user_id: UserId, payload: CompanionUserConfigAdminUpdateSchema, service: Service
) -> CompanionUserConfigAdminSchema:
    """Override tunables for one account."""
    return await service.update_user_config(user_id, payload)


@router.post(
    "/users/{user_id}/config/reset",
    response_model=CompanionUserConfigAdminSchema,
    operation_id="resetCompanionUserConfigAdmin",
)
async def reset_user_config(user_id: UserId, service: Service) -> CompanionUserConfigAdminSchema:
    """Drop every per-account override."""
    return await service.reset_user_config(user_id)


@router.get(
    "/users/{user_id}/companions/{companion_ref}/fragments",
    response_model=CompanionUserFragmentsSchema,
    operation_id="listCompanionUserFragmentsAdmin",
)
async def list_user_fragments(
    user_id: UserId, companion_ref: CompanionRef, service: Service, locale: Locale = "en"
) -> CompanionUserFragmentsSchema:
    """The account's effective story items and their progress."""
    return await service.user_fragments(user_id, companion_ref, locale)


@router.patch(
    "/users/{user_id}/companions/{companion_ref}/bond",
    response_model=CompanionUserAdminSchema,
    operation_id="updateCompanionUserBondAdmin",
)
async def update_bond(
    user_id: UserId,
    companion_ref: CompanionRef,
    payload: CompanionBondAdminUpdateSchema,
    service: Service,
) -> CompanionUserAdminSchema:
    """Adjust the account's bond counters with one companion."""
    return await service.update_bond(user_id, companion_ref, payload)


@router.put(
    "/users/{user_id}/companions/{companion_ref}/progress",
    response_model=CompanionUserFragmentsSchema,
    operation_id="setCompanionUserFragmentProgressAdmin",
)
async def set_fragment_progress(
    user_id: UserId,
    companion_ref: CompanionRef,
    payload: CompanionFragmentProgressUpdateSchema,
    service: Service,
) -> CompanionUserFragmentsSchema:
    """Mark one fragment told or untold for the account."""
    return await service.set_fragment_progress(user_id, companion_ref, payload)


@router.post(
    "/users/{user_id}/companions/{companion_ref}/progress/reset",
    response_model=CompanionUserAdminSchema,
    operation_id="resetCompanionUserProgressAdmin",
)
async def reset_progress(
    user_id: UserId,
    companion_ref: CompanionRef,
    payload: CompanionProgressResetSchema,
    service: Service,
) -> CompanionUserAdminSchema:
    """Reset told history, bond counters, or both."""
    return await service.reset_progress(user_id, companion_ref, payload)


@router.get(
    "/users/{user_id}/companions/{companion_ref}/persona",
    response_model=CompanionPersonaOverrideSchema,
    operation_id="getCompanionUserPersonaOverrideAdmin",
)
async def get_persona_override(
    user_id: UserId, companion_ref: CompanionRef, service: Service, locale: Locale = "en"
) -> CompanionPersonaOverrideSchema:
    """Root's persona override for the account, and what it would inherit."""
    return await service.get_persona_override(user_id, companion_ref, locale)


@router.put(
    "/users/{user_id}/companions/{companion_ref}/persona",
    response_model=CompanionPersonaOverrideSchema,
    operation_id="updateCompanionUserPersonaOverrideAdmin",
)
async def update_persona_override(
    user_id: UserId,
    companion_ref: CompanionRef,
    payload: CompanionPersonaOverrideUpdateSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionPersonaOverrideSchema:
    """Set root's persona for this account (the account's own edits still win)."""
    return await service.update_persona_override(user_id, companion_ref, locale, payload)


@router.post(
    "/users/{user_id}/companions/{companion_ref}/persona/reset",
    response_model=CompanionPersonaOverrideSchema,
    operation_id="resetCompanionUserPersonaOverrideAdmin",
)
async def reset_persona_override(
    user_id: UserId, companion_ref: CompanionRef, service: Service, locale: Locale = "en"
) -> CompanionPersonaOverrideSchema:
    """Remove root's persona override."""
    return await service.reset_persona_override(user_id, companion_ref, locale)


@router.get(
    "/users/{user_id}/companions/{companion_ref}/lore-overrides",
    response_model=list[CompanionLoreOverrideSchema],
    operation_id="listCompanionUserLoreOverridesAdmin",
)
async def list_lore_overrides(
    user_id: UserId, companion_ref: CompanionRef, service: Service, locale: Locale = "en"
) -> list[CompanionLoreOverrideSchema]:
    """Root's replace / add / hide changes for this account."""
    return await service.list_lore_overrides(user_id, companion_ref, locale)


@router.put(
    "/users/{user_id}/companions/{companion_ref}/lore-overrides",
    response_model=CompanionLoreOverrideSchema,
    operation_id="upsertCompanionUserLoreOverrideAdmin",
)
async def upsert_lore_override(
    user_id: UserId,
    companion_ref: CompanionRef,
    payload: CompanionLoreOverrideUpsertSchema,
    service: Service,
    locale: Locale = "en",
) -> CompanionLoreOverrideSchema:
    """Create or replace one lore override for this account."""
    return await service.upsert_lore_override(user_id, companion_ref, locale, payload)


@router.delete(
    "/users/{user_id}/companions/{companion_ref}/lore-overrides/{fragment_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCompanionUserLoreOverrideAdmin",
)
async def delete_lore_override(
    user_id: UserId,
    companion_ref: CompanionRef,
    fragment_key: FragmentKey,
    service: Service,
    locale: Locale = "en",
) -> Response:
    """Remove one lore override."""
    await service.delete_lore_override(user_id, companion_ref, locale, fragment_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/users/{user_id}/stories",
    response_model=list[CompanionGeneratedStorySummarySchema],
    operation_id="listCompanionGeneratedStoriesAdmin",
)
async def list_stories(
    user_id: UserId, service: Service
) -> list[CompanionGeneratedStorySummarySchema]:
    """Generated life stories without their text (listing is not logged)."""
    return await service.list_stories(user_id)


@router.get(
    "/users/{user_id}/stories/{story_id}",
    response_model=CompanionGeneratedStorySchema,
    operation_id="getCompanionGeneratedStoryAdmin",
)
async def get_story(
    user_id: UserId, story_id: Annotated[int, Path(ge=1)], service: Service
) -> CompanionGeneratedStorySchema:
    """Read a generated story's full text. Every read is recorded."""
    return await service.get_story(user_id, story_id)


@router.patch(
    "/users/{user_id}/stories/{story_id}",
    response_model=CompanionGeneratedStorySchema,
    operation_id="updateCompanionGeneratedStoryAdmin",
)
async def update_story(
    user_id: UserId,
    story_id: Annotated[int, Path(ge=1)],
    payload: CompanionGeneratedStoryUpdateSchema,
    service: Service,
) -> CompanionGeneratedStorySchema:
    """Edit, publish, or retire a generated story."""
    return await service.update_story(user_id, story_id, payload)


@router.delete(
    "/users/{user_id}/stories/{story_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteCompanionGeneratedStoryAdmin",
)
async def delete_story(
    user_id: UserId, story_id: Annotated[int, Path(ge=1)], service: Service
) -> Response:
    """Delete a generated story and its told history."""
    await service.delete_story(user_id, story_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/stories/{story_id}/regenerate",
    response_model=CompanionStoryJobSchema,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="regenerateCompanionGeneratedStoryAdmin",
)
async def regenerate_story(
    user_id: UserId, story_id: Annotated[int, Path(ge=1)], service: Service
) -> CompanionStoryJobSchema:
    """Queue a replacement for a generated story."""
    return await service.regenerate_story(user_id, story_id)


@router.post(
    "/users/{user_id}/stories",
    response_model=CompanionStoryJobSchema,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="generateCompanionStoryAdmin",
)
async def generate_story(
    user_id: UserId, payload: CompanionStoryGenerateSchema, service: Service
) -> CompanionStoryJobSchema:
    """Queue a life story for this account now (the worker writes it)."""
    return await service.generate_story(user_id, payload)


@router.get(
    "/users/{user_id}/jobs",
    response_model=list[CompanionStoryJobSchema],
    operation_id="listCompanionStoryJobsAdmin",
)
async def list_jobs(user_id: UserId, service: Service) -> list[CompanionStoryJobSchema]:
    """Recent life-story jobs for the account."""
    return await service.list_jobs(user_id)


@router.post(
    "/users/{user_id}/jobs/{job_id}/cancel",
    response_model=CompanionStoryJobSchema,
    operation_id="cancelCompanionStoryJobAdmin",
)
async def cancel_job(
    user_id: UserId, job_id: Annotated[int, Path(ge=1)], service: Service
) -> CompanionStoryJobSchema:
    """Cancel a queued job, or ask a running one to stop."""
    return await service.cancel_job(user_id, job_id)


@router.get(
    "/users/{user_id}/access-log",
    response_model=list[CompanionAccessLogSchema],
    operation_id="listCompanionAccessLogAdmin",
)
async def list_access_log(user_id: UserId, service: Service) -> list[CompanionAccessLogSchema]:
    """Root's recorded reads and changes of this account's companion stories."""
    return await service.list_access(user_id)
