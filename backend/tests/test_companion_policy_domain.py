"""Pure tests for companion policy resolution and story layering."""

import asyncio
from dataclasses import fields

from app.module.companion.domain.companion_policy_domain import (
    AccountCompanionPolicy,
    AdminLoreOverride,
    StoryLayers,
    allowed_refs,
    apply_admin_overrides,
    merge_config_overrides,
    resolve_active_companion,
    resolve_persona,
    resolve_story_items,
)
from app.module.companion.domain.story_domain import (
    CompanionRuntimeConfig,
    CompanionStoryConfig,
    LoreFragment,
    StoryItem,
)
from app.module.companion.service.seed_catalog import seed_runtime_config
from app.module.companion.service.story_config import (
    StaticCompanionContentProvider,
    StaticCompanionPolicyProvider,
    StaticStoryConfigProvider,
)

PRESETS = ["vellum", "atlas", "herbaria"]
CUSTOM = ["custom:7"]


def _item(key: str, text: str = "t", origin: str = "preset") -> StoryItem:
    return StoryItem(key=key, text=text, themes=(), tier="first", origin=origin)  # type: ignore[arg-type]


def test_user_choice_wins_when_allowed() -> None:
    choice = resolve_active_companion(
        user_selected="preset:atlas",
        policy=AccountCompanionPolicy(default_ref="preset:herbaria"),
        global_default="preset:vellum",
        enabled_presets=PRESETS,
        custom_refs=CUSTOM,
    )
    assert (choice.ref, choice.source, choice.pinned) == ("preset:atlas", "user", False)


def test_pin_beats_user_choice() -> None:
    choice = resolve_active_companion(
        user_selected="preset:atlas",
        policy=AccountCompanionPolicy(pinned_ref="preset:herbaria", pin_enabled=True),
        global_default="preset:vellum",
        enabled_presets=PRESETS,
        custom_refs=CUSTOM,
    )
    assert (choice.ref, choice.source, choice.pinned) == ("preset:herbaria", "pinned", True)


def test_disabled_pin_is_ignored() -> None:
    choice = resolve_active_companion(
        user_selected="preset:atlas",
        policy=AccountCompanionPolicy(pinned_ref="preset:herbaria", pin_enabled=False),
        global_default="preset:vellum",
        enabled_presets=PRESETS,
        custom_refs=CUSTOM,
    )
    assert choice.ref == "preset:atlas"


def test_disallowed_user_choice_falls_back_to_admin_default_then_global() -> None:
    policy = AccountCompanionPolicy(
        default_ref="preset:herbaria",
        allowed_refs=("preset:vellum", "preset:herbaria"),
    )
    choice = resolve_active_companion(
        user_selected="preset:atlas",
        policy=policy,
        global_default="preset:vellum",
        enabled_presets=PRESETS,
        custom_refs=[],
    )
    assert (choice.ref, choice.source) == ("preset:herbaria", "admin_default")
    no_default = AccountCompanionPolicy(allowed_refs=("preset:vellum",))
    fallback = resolve_active_companion(
        user_selected="preset:atlas",
        policy=no_default,
        global_default="preset:vellum",
        enabled_presets=PRESETS,
        custom_refs=[],
    )
    assert (fallback.ref, fallback.source) == ("preset:vellum", "global_default")


def test_user_choice_returns_when_allowed_again() -> None:
    narrowed = AccountCompanionPolicy(allowed_refs=("preset:vellum",))
    widened = AccountCompanionPolicy()
    kwargs = {
        "user_selected": "preset:atlas",
        "global_default": "preset:vellum",
        "enabled_presets": PRESETS,
        "custom_refs": [],
    }
    assert resolve_active_companion(policy=narrowed, **kwargs).ref == "preset:vellum"  # type: ignore[arg-type]
    assert resolve_active_companion(policy=widened, **kwargs).ref == "preset:atlas"  # type: ignore[arg-type]


def test_custom_companions_follow_allow_custom() -> None:
    assert "custom:7" in allowed_refs(
        AccountCompanionPolicy(allowed_refs=("preset:vellum",)),
        enabled_presets=PRESETS,
        custom_refs=CUSTOM,
    )
    assert "custom:7" not in allowed_refs(
        AccountCompanionPolicy(allow_custom=False),
        enabled_presets=PRESETS,
        custom_refs=CUSTOM,
    )


def test_persona_layer_order() -> None:
    assert (
        resolve_persona(
            user_persona=None,
            admin_persona="admin",
            preset_persona="preset",
            english_preset_persona="english",
            fallback="fallback",
        )
        == "admin"
    )
    assert (
        resolve_persona(
            user_persona="mine",
            admin_persona="admin",
            preset_persona="preset",
            english_preset_persona="english",
            fallback="fallback",
        )
        == "mine"
    )
    assert (
        resolve_persona(
            user_persona=None,
            admin_persona=None,
            preset_persona=None,
            english_preset_persona="english",
            fallback="fallback",
        )
        == "english"
    )


def test_admin_overrides_replace_add_hide() -> None:
    items = (_item("a-001", "one"), _item("a-002", "two"), _item("a-003", "three"))
    overrides = (
        AdminLoreOverride(key="a-001", action="replace", item=_item("a-001", "ONE", "admin")),
        AdminLoreOverride(key="a-002", action="hide"),
        AdminLoreOverride(
            key="x-001", action="add", item=_item("x-001", "new", "admin"), position=0
        ),
    )
    result = apply_admin_overrides(items, overrides)
    assert [item.key for item in result] == ["x-001", "a-001", "a-003"]
    assert result[1].text == "ONE"


def test_user_copy_replaces_admin_layer_and_generated_is_appended() -> None:
    layers = StoryLayers(
        preset_items=(_item("a-001"),),
        admin_overrides=(AdminLoreOverride(key="a-001", action="hide"),),
        user_items=(_item("u-1", origin="user"),),
        generated_items=(_item("g-1", origin="generated"),),
    )
    assert [item.key for item in resolve_story_items(layers)] == ["u-1", "g-1"]
    without_user = StoryLayers(
        preset_items=(_item("a-001"), _item("a-002")),
        admin_overrides=(AdminLoreOverride(key="a-001", action="hide"),),
        generated_items=(_item("g-1", origin="generated"),),
    )
    assert [item.key for item in resolve_story_items(without_user)] == ["a-002", "g-1"]


def test_merge_config_overrides_ignores_null_and_unknown() -> None:
    merged = merge_config_overrides(
        {"story_moment_every_runs": 3, "untold_bonus": 0.06},
        {"story_moment_every_runs": 5, "untold_bonus": None, "unknown": 1},
    )
    assert merged == {"story_moment_every_runs": 5, "untold_bonus": 0.06}


def test_lore_fragment_alias_and_origin_default() -> None:
    assert LoreFragment is StoryItem
    assert StoryItem(key="k", text="t", themes=(), tier="first").origin == "preset"


def test_static_providers_serve_seed() -> None:
    config = asyncio.run(StaticStoryConfigProvider().load(None))
    assert isinstance(config, CompanionRuntimeConfig)
    assert config.template("persona_rules") == seed_runtime_config().template("persona_rules")
    seed = seed_runtime_config()
    plain = CompanionStoryConfig(
        **{
            **{field.name: getattr(seed, field.name) for field in fields(CompanionStoryConfig)},
            "story_moment_every_runs": 9,
        }
    )
    lifted = asyncio.run(StaticStoryConfigProvider(plain).load(1))
    assert lifted.story_moment_every_runs == 9
    assert lifted.template("lore_guidance")

    content = StaticCompanionContentProvider()
    ids = asyncio.run(content.enabled_preset_ids())
    assert ids[0] == "vellum" and len(ids) == 6
    assert asyncio.run(content.global_default_preset_id()) == "vellum"
    vellum = asyncio.run(content.preset("vellum", "zh-TW"))
    assert vellum is not None and vellum.fragments
    canon = asyncio.run(content.canon("zh-TW"))
    assert "apsor-archive" in canon
    bible = asyncio.run(content.world_doc("bible", "en"))
    assert bible is not None and bible.kind == "bible" and bible.body_md
    character = asyncio.run(content.world_doc("character:vellum", "en"))
    assert character is not None and character.kind == "character"
    assert asyncio.run(content.world_doc("unknown", "en")) is None

    policy = asyncio.run(StaticCompanionPolicyProvider().load(1))
    assert policy == AccountCompanionPolicy()
