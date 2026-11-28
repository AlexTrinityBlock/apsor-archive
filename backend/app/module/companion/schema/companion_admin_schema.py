"""Schemas for the root companion administration surface (``/admin/companions``).

List endpoints never carry a generated story's full text: reading the text is a
separate, logged request (``getCompanionGeneratedStoryAdmin``).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.module.companion.domain.story_domain import (
    FRAGMENT_MAX_CHARS,
    PERSONA_MAX_CHARS,
)
from app.module.companion.schema.companion_story_schema import (
    LoreWeightField,
    StoryLocaleField,
)

OriginField = Literal["preset", "admin", "user", "generated"]
OverrideActionField = Literal["replace", "add", "hide"]
StoryStatusField = Literal["draft", "published", "retired"]
JobStatusField = Literal[
    "queued",
    "running",
    "succeeded",
    "skipped",
    "failed",
    "cancel_requested",
    "cancelled",
]
# Nothing is locked: a fragment has been told to the account, or not yet.
FragmentStateField = Literal["untold", "told"]
ToldSourceField = Literal["topical", "story_moment", "self_query", "admin", "recall"]
WorldDocKindField = Literal["bible", "glossary", "world", "terms", "character"]
ProgressResetScope = Literal["told", "bond", "all"]

STORY_TEXT_MAX_CHARS = 4000
WORLD_DOC_MAX_CHARS = 200_000
TEMPLATE_MAX_CHARS = 20_000


class _Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Global content -------------------------------------------------------


class CompanionPresetAdminSchema(BaseModel):
    """One preset librarian as root sees it."""

    id: str
    position: int
    enabled: bool
    is_global_default: bool
    names: dict[str, str] = Field(description="Display name per locale.")
    fragment_count: int
    admin_modified: bool
    upstream_changed: bool
    seeded: bool = Field(description="False when the row only exists in the seed files.")


class CompanionPresetAdminUpdateSchema(_Forbid):
    """Enable, reorder, or make a preset the global default."""

    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0, le=999)
    is_global_default: bool | None = None


class CompanionPresetTextAdminSchema(BaseModel):
    """A preset's name and persona in one locale."""

    preset_id: str
    locale: StoryLocaleField
    name: str
    persona: str
    admin_modified: bool
    upstream_changed: bool
    updated_at: datetime | None = None


class CompanionPresetTextAdminUpdateSchema(_Forbid):
    """Replace a preset's name or persona in one locale."""

    name: str | None = Field(default=None, min_length=1, max_length=40)
    persona: str | None = Field(default=None, min_length=1, max_length=PERSONA_MAX_CHARS)


class CompanionLoreItemAdminSchema(BaseModel):
    """One global lore item with its text in the requested locale."""

    id: int
    preset_id: str
    fragment_key: str
    weight: LoreWeightField
    themes: list[str]
    refs: list[str]
    position: int
    text: str
    text_locale: StoryLocaleField
    retired: bool
    admin_modified: bool
    upstream_changed: bool


class CompanionLoreItemAdminCreateSchema(_Forbid):
    """Add a lore item to a preset."""

    preset_id: str = Field(min_length=1, max_length=48)
    fragment_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    weight: LoreWeightField
    themes: list[str] = Field(default_factory=list, max_length=12)
    refs: list[str] = Field(default_factory=list, max_length=12)
    text: str = Field(min_length=1, max_length=FRAGMENT_MAX_CHARS)
    locale: StoryLocaleField = "en"


class CompanionLoreItemAdminUpdateSchema(_Forbid):
    """Edit a lore item's metadata or its text in one locale."""

    weight: LoreWeightField | None = None
    themes: list[str] | None = Field(default=None, max_length=12)
    refs: list[str] | None = Field(default=None, max_length=12)
    position: int | None = Field(default=None, ge=0, le=9999)
    text: str | None = Field(default=None, min_length=1, max_length=FRAGMENT_MAX_CHARS)
    locale: StoryLocaleField = "en"


class CompanionWorldDocSummarySchema(BaseModel):
    """One world document without its body."""

    doc_key: str
    locale: StoryLocaleField
    kind: WorldDocKindField
    title: str
    version: int
    chars: int
    admin_modified: bool
    upstream_changed: bool
    updated_at: datetime | None = None


class CompanionWorldDocSchema(CompanionWorldDocSummarySchema):
    """One world document with its markdown body."""

    body_md: str


class CompanionWorldDocUpdateSchema(_Forbid):
    """Replace a world document; ``version`` guards concurrent edits."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    body_md: str = Field(min_length=1, max_length=WORLD_DOC_MAX_CHARS)
    version: int = Field(ge=1)


class CompanionWorldDocRevisionSchema(BaseModel):
    """A previous version of a world document."""

    id: int
    version: int
    body_md: str
    created_at: datetime
    created_by_user_id: int | None = None


class CompanionCanonEntitySchema(BaseModel):
    """One canon entity in one locale."""

    entity_id: str
    locale: StoryLocaleField
    name: str
    summary: str
    admin_modified: bool


class CompanionCanonEntityUpsertSchema(_Forbid):
    """Create or replace a canon entity in one locale."""

    entity_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    locale: StoryLocaleField = "en"
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1000)


class CompanionConfigKnobSchema(BaseModel):
    """One tunable with its value, seed default, and bounds."""

    key: str
    value: float | int | bool | str | list[str]
    default: float | int | bool | str | list[str]
    kind: Literal["int", "float", "bool", "weight", "list", "datetime"]
    minimum: float | None = None
    maximum: float | None = None
    group: Literal["recall", "pacing", "life_story", "words"]


class CompanionConfigAdminSchema(BaseModel):
    """Every story tunable, with seed defaults for comparison."""

    version: int
    knobs: list[CompanionConfigKnobSchema]
    updated_at: datetime | None = None


class CompanionConfigAdminUpdateSchema(_Forbid):
    """Set one or more tunables by key."""

    values: dict[str, float | int | bool | str | list[str]] = Field(min_length=1)


class CompanionTemplateAdminSchema(BaseModel):
    """One guidance string or prompt template."""

    template_key: str
    locale: StoryLocaleField
    body: str
    required_placeholders: list[str]
    missing_placeholders: list[str]
    version: int
    admin_modified: bool
    upstream_changed: bool


class CompanionTemplateAdminUpdateSchema(_Forbid):
    """Replace a template body in one locale."""

    body: str = Field(min_length=1, max_length=TEMPLATE_MAX_CHARS)


class CompanionTemplatePreviewRequestSchema(_Forbid):
    """Render a template against a synthetic sample (never a real archive)."""

    template_key: str = Field(min_length=1, max_length=48)
    locale: StoryLocaleField = "en"
    body: str | None = Field(default=None, max_length=TEMPLATE_MAX_CHARS)


class CompanionTemplatePreviewSchema(BaseModel):
    """The rendered sample and any placeholder problems."""

    rendered: str
    missing_placeholders: list[str]
    unknown_placeholders: list[str]


class CompanionSeedStatusSchema(BaseModel):
    """Whether the shipped seed bundle has been applied, and what drifted."""

    applied: bool
    seed_version: int | None = None
    content_version: int | None = None
    applied_at: datetime | None = None
    shipped_presets: int
    shipped_fragments: int
    database_presets: int
    database_fragments: int
    admin_modified_rows: int
    upstream_changed_rows: int


class CompanionSeedApplySchema(_Forbid):
    """Re-apply the shipped seed; ``force_keys`` overwrite admin edits."""

    force_keys: list[str] = Field(default_factory=list, max_length=500)


# --- Per user ---------------------------------------------------------------


class CompanionBondAdminSchema(BaseModel):
    """One account's bond with one companion."""

    companion_ref: str
    name: str
    completed_runs: int
    conversations: int
    first_met_at: datetime | None = None
    last_story_run: int | None = None
    next_story_moment_in_runs: int | None = None
    next_life_story_in_conversations: int | None = None
    told_count: int
    fragment_count: int
    generated_count: int
    admin_adjusted_at: datetime | None = None


class CompanionUserSummarySchema(BaseModel):
    """One account in the companion directory."""

    user_id: int
    username: str
    display_name: str | None = None
    role: str
    is_active: bool
    active_ref: str | None = None
    enabled: bool
    completed_runs: int
    told_count: int
    generated_count: int
    last_activity_at: datetime | None = None
    activity: list[int] = Field(description="Told fragments per week, oldest first (8 weeks).")


class CompanionPolicyAdminSchema(BaseModel):
    """Root's companion policy for one account."""

    user_id: int
    default_ref: str | None = None
    allowed_refs: list[str] | None = None
    allow_custom: bool = True
    pinned_ref: str | None = None
    pin_enabled: bool = False
    options: list[str] = Field(description="Every ref root could allow for this account.")
    active_ref: str
    active_source: Literal["pinned", "user", "admin_default", "global_default"]
    user_selected: str | None = None
    updated_at: datetime | None = None


class CompanionPolicyAdminUpdateSchema(_Forbid):
    """Replace root's companion policy for one account."""

    default_ref: str | None = Field(default=None, max_length=64)
    allowed_refs: list[str] | None = Field(default=None, max_length=64)
    allow_custom: bool = True
    pinned_ref: str | None = Field(default=None, max_length=64)
    pin_enabled: bool = False


class CompanionUserAdminSchema(BaseModel):
    """Everything root sees about one account's companions."""

    user_id: int
    username: str
    display_name: str | None = None
    policy: CompanionPolicyAdminSchema
    bonds: list[CompanionBondAdminSchema]
    custom_companions: list[str]


class CompanionUserConfigAdminSchema(BaseModel):
    """Per-account overrides: ``value`` is null when the global value applies."""

    user_id: int
    knobs: list[CompanionConfigKnobSchema]
    overrides: dict[str, float | int | bool | str | None]
    updated_at: datetime | None = None


class CompanionUserConfigAdminUpdateSchema(_Forbid):
    """Set per-account overrides; a null value inherits the global setting."""

    values: dict[str, float | int | bool | str | None] = Field(min_length=1)


class CompanionUserFragmentSchema(BaseModel):
    """One effective story item for an account, with its progress."""

    key: str
    origin: OriginField
    weight: LoreWeightField
    themes: list[str]
    refs: list[str]
    text: str
    state: FragmentStateField
    told_count: int
    offered_at: datetime | None = None
    last_told_at: datetime | None = None
    source: ToldSourceField | None = None
    hidden_by_admin: bool = False


class CompanionUserFragmentsSchema(BaseModel):
    """An account's effective story items for one companion and locale."""

    user_id: int
    companion_ref: str
    locale: StoryLocaleField
    fragments: list[CompanionUserFragmentSchema]


class CompanionBondAdminUpdateSchema(_Forbid):
    """Adjust an account's bond (e.g. grant progress)."""

    completed_runs: int | None = Field(default=None, ge=0, le=1_000_000)
    conversations: int | None = Field(default=None, ge=0, le=1_000_000)


class CompanionFragmentProgressUpdateSchema(_Forbid):
    """Mark a fragment told (or untold) for an account."""

    fragment_key: str = Field(min_length=1, max_length=64)
    told: bool


class CompanionProgressResetSchema(_Forbid):
    """Reset told history, the bond counters, or both."""

    scope: ProgressResetScope = "told"


class CompanionPersonaOverrideSchema(BaseModel):
    """Root's persona override for one account, companion, and locale."""

    user_id: int
    companion_ref: str
    locale: StoryLocaleField
    persona: str | None = None
    inherited_persona: str
    updated_at: datetime | None = None


class CompanionPersonaOverrideUpdateSchema(_Forbid):
    """Replace root's persona override."""

    persona: str = Field(min_length=1, max_length=PERSONA_MAX_CHARS)


class CompanionLoreOverrideSchema(BaseModel):
    """Root's replace / add / hide of one fragment for one account."""

    fragment_key: str
    action: OverrideActionField
    text: str | None = None
    weight: LoreWeightField | None = None
    themes: list[str]
    refs: list[str]
    position: int | None = None
    updated_at: datetime | None = None


class CompanionLoreOverrideUpsertSchema(_Forbid):
    """Create or replace an override for one fragment key."""

    fragment_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    action: OverrideActionField
    text: str | None = Field(default=None, max_length=FRAGMENT_MAX_CHARS)
    weight: LoreWeightField | None = None
    themes: list[str] = Field(default_factory=list, max_length=12)
    refs: list[str] = Field(default_factory=list, max_length=12)
    position: int | None = Field(default=None, ge=0, le=9999)


class CompanionGeneratedStorySummarySchema(BaseModel):
    """A generated life story without its text (listing never logs a view)."""

    id: int
    companion_ref: str
    locale: StoryLocaleField
    title: str
    status: StoryStatusField
    weight: LoreWeightField
    chars: int
    model: str | None = None
    source_counts: dict[str, int]
    told_count: int
    admin_edited_at: datetime | None = None
    created_at: datetime


class CompanionGeneratedStorySchema(CompanionGeneratedStorySummarySchema):
    """A generated life story with its full text (reading it is logged)."""

    text: str
    themes: list[str]
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    template_version: int | None = None


class CompanionGeneratedStoryUpdateSchema(_Forbid):
    """Edit a generated story's title, text, weight, or status."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    text: str | None = Field(default=None, min_length=1, max_length=STORY_TEXT_MAX_CHARS)
    weight: LoreWeightField | None = None
    status: StoryStatusField | None = None


class CompanionStoryGenerateSchema(_Forbid):
    """Queue an admin life-story job (always lands as a draft for review)."""

    companion_ref: str = Field(min_length=1, max_length=64)
    locale: StoryLocaleField = "en"


class CompanionStoryJobSchema(BaseModel):
    """One life-story job."""

    id: int
    companion_ref: str
    locale: StoryLocaleField
    trigger: Literal["cadence", "admin", "regenerate"]
    status: JobStatusField
    skip_reason: str | None = None
    error_code: str | None = None
    attempts: int
    replaces_story_id: int | None = None
    created_at: datetime
    finished_at: datetime | None = None


class CompanionAccessLogSchema(BaseModel):
    """One logged root action on an account's companion stories."""

    id: int
    actor_user_id: int
    story_id: int | None = None
    companion_ref: str | None = None
    action: str
    at: datetime


# --- User facing ------------------------------------------------------------


class CompanionPresetOptionSchema(BaseModel):
    """A preset this account may choose."""

    id: str
    ref: str
    name: str
    position: int


class CompanionPresetCatalogSchema(BaseModel):
    """Allowed presets plus how the active companion was resolved."""

    presets: list[CompanionPresetOptionSchema]
    allowed_refs: list[str]
    allow_custom: bool
    active_ref: str
    active_source: Literal["pinned", "user", "admin_default", "global_default"]
    pinned: bool
