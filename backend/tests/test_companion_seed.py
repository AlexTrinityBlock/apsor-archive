"""The companion seed bundle, the seeder, and the database-backed providers."""

import asyncio
import dataclasses
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.database.session import Database
from app.module.companion.domain.seed_domain import CONFIG_COLUMNS
from app.module.companion.domain.story_domain import TEMPLATE_KEYS, missing_placeholders
from app.module.companion.repository.companion_providers import (
    DbCompanionConfigProvider,
    DbCompanionContentProvider,
    DbCompanionPolicyProvider,
)
from app.module.companion.service.companion_seeder import CompanionSeeder, SeedResult
from app.module.companion.service.seed_catalog import (
    SeedBundle,
    load_seed_bundle,
    seed_runtime_config,
)
from app.module.companion.service.story_config import (
    StaticCompanionContentProvider,
    StaticStoryConfigProvider,
)
from tests.conftest import TEST_DATABASE_URL

CONVERSATIONS = "/api/v1/agent/conversations"


def _seed(bundle: SeedBundle | None = None) -> SeedResult:
    async def run() -> SeedResult:
        database = Database(TEST_DATABASE_URL)
        try:
            return await CompanionSeeder(bundle).run(database)
        finally:
            await database.dispose()

    return asyncio.run(run())


def _with_rows(bundle: SeedBundle, table: str, rows: list[dict[str, Any]]) -> SeedBundle:
    """Return a bundle whose ``table`` rows (and therefore hash) changed."""
    import hashlib
    import json

    def rehash(row: dict[str, Any]) -> dict[str, Any]:
        body = {key: value for key, value in row.items() if key != "seed_hash"}
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {**body, "seed_hash": hashlib.sha256(payload.encode()).hexdigest()}

    new_rows = {**bundle.rows, table: [rehash(row) for row in rows]}
    marker = hashlib.sha256(json.dumps(new_rows, sort_keys=True, default=str).encode()).hexdigest()
    return dataclasses.replace(bundle, rows=new_rows, content_hash=marker)


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


# --- the bundle -----------------------------------------------------------------


def test_bundle_covers_every_live_table_and_template() -> None:
    bundle = load_seed_bundle()
    assert bundle.preset_order[0] == bundle.global_default == "vellum"
    assert len(bundle.rows["companion_preset"]) == 6
    assert {row["template_key"] for row in bundle.rows["companion_prompt_template"]} == set(
        TEMPLATE_KEYS
    )
    for row in bundle.rows["companion_prompt_template"]:
        assert not missing_placeholders(row["template_key"], row["body"])
    config = bundle.rows["companion_config"][0]
    assert set(CONFIG_COLUMNS) <= set(config)
    locales = {row["locale"] for row in bundle.rows["companion_lore_item_text"]}
    assert locales == {"en", "zh-TW", "zh-CN"}
    docs = {(row["doc_key"], row["locale"]) for row in bundle.rows["companion_world_doc"]}
    assert ("bible", "en") in docs and ("character:vellum", "en") in docs
    assert ("terms", "zh-TW") in docs
    # Every seed row carries the hash the seeder compares.
    assert all(row["seed_hash"] for rows in bundle.rows.values() for row in rows)


def test_seed_config_drives_the_runtime_config() -> None:
    config = seed_runtime_config()
    assert config.self_query_phrases and config.banned_address_terms
    assert "keeper" in config.banned_address_terms
    assert config.persona_rules and config.lore_guidance and config.story_moment_guidance
    assert "{name}" in config.template("custom_persona_default")
    life_user = config.template("life_story_user")
    assert "{memories}" in life_user and "{canon}" in life_user


# --- the seeder -------------------------------------------------------------------


def test_seeder_is_a_no_op_when_the_bundle_is_applied(owner_engine: Engine) -> None:
    before = _scalar(owner_engine, "SELECT content_version FROM companion_seed_state")
    result = _seed()
    assert result.applied is False
    assert _scalar(owner_engine, "SELECT content_version FROM companion_seed_state") == before


def test_seeder_fills_an_empty_world(owner_engine: Engine) -> None:
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE companion_seed_state, companion_preset, companion_canon_entity, "
                "companion_world_doc, companion_prompt_template, companion_config CASCADE"
            )
        )
    result = _seed()
    assert result.applied is True and result.inserted > 900
    assert _scalar(owner_engine, "SELECT count(*) FROM companion_lore_item") == len(
        load_seed_bundle().rows["companion_lore_item"]
    )
    assert _scalar(owner_engine, "SELECT count(*) FROM companion_prompt_template") == len(
        TEMPLATE_KEYS
    )
    assert (
        _scalar(
            owner_engine,
            "SELECT count(*) FROM companion_preset WHERE is_global_default",
        )
        == 1
    )
    assert _seed().applied is False


def test_seeder_keeps_admin_edits_and_flags_upstream_changes(owner_engine: Engine) -> None:
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE companion_preset_text SET persona = 'Root wrote this.', "
                "admin_modified = true WHERE preset_id = 'atlas' AND locale = 'en'"
            )
        )
        connection.execute(
            text(
                "UPDATE companion_config SET story_moment_every_runs = 9, "
                "admin_modified = true WHERE id = 1"
            )
        )
    bundle = load_seed_bundle()
    texts = [
        {**row, "persona": row["persona"] + " (revised upstream)"}
        if row["locale"] == "en" and row["preset_id"] in {"atlas", "quill"}
        else row
        for row in bundle.rows["companion_preset_text"]
    ]
    changed = _with_rows(bundle, "companion_preset_text", texts)
    config_rows = [{**bundle.rows["companion_config"][0], "self_query_window": 7}]
    changed = _with_rows(changed, "companion_config", config_rows)
    version_before = _scalar(owner_engine, "SELECT content_version FROM companion_seed_state")

    result = _seed(changed)

    assert result.applied is True
    assert result.flagged == 2 and result.updated >= 1
    assert (
        _scalar(
            owner_engine,
            "SELECT persona FROM companion_preset_text WHERE preset_id = 'atlas' AND locale = 'en'",
        )
        == "Root wrote this."
    )
    assert _scalar(
        owner_engine,
        "SELECT upstream_seed_hash IS NOT NULL FROM companion_preset_text "
        "WHERE preset_id = 'atlas' AND locale = 'en'",
    )
    assert _scalar(
        owner_engine,
        "SELECT persona FROM companion_preset_text WHERE preset_id = 'quill' AND locale = 'en'",
    ).endswith("(revised upstream)")
    assert _scalar(owner_engine, "SELECT story_moment_every_runs FROM companion_config") == 9
    assert _scalar(owner_engine, "SELECT self_query_window FROM companion_config") == 6
    assert _scalar(owner_engine, "SELECT upstream_seed_hash IS NOT NULL FROM companion_config")
    assert _scalar(owner_engine, "SELECT content_version FROM companion_seed_state") == (
        version_before + 1
    )


def test_seeder_retires_removed_lore_and_restores_it(owner_engine: Engine) -> None:
    bundle = load_seed_bundle()
    gone = ("vellum", "vellum-002")
    items = [
        row
        for row in bundle.rows["companion_lore_item"]
        if (row["preset_id"], row["fragment_key"]) != gone
    ]
    item_texts = [
        row
        for row in bundle.rows["companion_lore_item_text"]
        if (row["preset_id"], row["fragment_key"]) != gone
    ]
    trimmed = _with_rows(
        _with_rows(bundle, "companion_lore_item", items), "companion_lore_item_text", item_texts
    )
    assert _seed(trimmed).retired == 1
    assert _scalar(
        owner_engine,
        "SELECT retired_at IS NOT NULL FROM companion_lore_item WHERE fragment_key = 'vellum-002'",
    )
    # Retired items are never deleted (told progress keeps its meaning) and come
    # back when the seed ships them again.
    restored = _with_rows(bundle, "companion_lore_item", bundle.rows["companion_lore_item"])
    _seed(restored)
    assert _scalar(
        owner_engine,
        "SELECT retired_at IS NULL FROM companion_lore_item WHERE fragment_key = 'vellum-002'",
    )


# --- the providers -------------------------------------------------------------------


def _providers() -> tuple[Database, DbCompanionContentProvider, DbCompanionConfigProvider]:
    database = Database(TEST_DATABASE_URL)
    content = DbCompanionContentProvider(
        database, fallback=StaticCompanionContentProvider(), ttl_seconds=0
    )
    config = DbCompanionConfigProvider(
        database, fallback=StaticStoryConfigProvider(), ttl_seconds=0
    )
    return database, content, config


def test_content_provider_serves_the_live_rows(owner_engine: Engine) -> None:
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE companion_lore_item_text SET text = 'Root rewrote this passage.' "
                "WHERE locale = 'en' AND item_id = (SELECT id FROM companion_lore_item "
                "WHERE fragment_key = 'vellum-001')"
            )
        )
        connection.execute(text("UPDATE companion_preset SET enabled = false WHERE id = 'quill'"))
        connection.execute(text("UPDATE companion_seed_state SET content_version = 99"))

    async def run() -> None:
        database, content, _config = _providers()
        try:
            assert await content.content_version() == 99
            ids = await content.enabled_preset_ids()
            assert ids[0] == "vellum" and "quill" not in ids
            assert await content.global_default_preset_id() == "vellum"
            vellum = await content.preset("vellum", "en")
            assert vellum is not None
            assert vellum.fragments[0].text == "Root rewrote this passage."
            zh = await content.preset("vellum", "zh-TW")
            assert zh is not None and zh.persona != vellum.persona
            # zh-TW keeps its own translation, while an untranslated item falls back.
            assert zh.fragments[0].text != "Root rewrote this passage."
            assert (await content.preset("quill", "en")) is not None  # disabled, still resolvable
            canon = await content.canon("zh-TW")
            assert canon["apsor-archive"].summary.startswith("Apsor")
            bible = await content.world_doc("bible", "zh-TW")
            assert bible is not None and bible.locale == "en"  # English fallback
        finally:
            await database.dispose()

    asyncio.run(run())


def test_config_provider_applies_account_overrides(
    owner_engine: Engine, client: TestClient
) -> None:
    user_id = _scalar(owner_engine, "SELECT id FROM app_user ORDER BY id LIMIT 1")
    with owner_engine.begin() as connection:
        connection.execute(text("UPDATE companion_config SET untold_bonus = 0.2, version = 5"))
        connection.execute(
            text(
                "INSERT INTO companion_user_config (user_id, story_moment_every_runs) "
                "VALUES (:user_id, 11)"
            ),
            {"user_id": user_id},
        )

    async def run() -> None:
        database, _content, config = _providers()
        try:
            global_config = await config.load(None)
            assert global_config.untold_bonus == pytest.approx(0.2)
            assert global_config.version == 5
            assert global_config.story_moment_every_runs == 3
            account = await config.load(user_id)
            assert account.story_moment_every_runs == 11
            assert account.untold_bonus == pytest.approx(0.2)
            assert account.lore_guidance == seed_runtime_config().lore_guidance
        finally:
            await database.dispose()

    asyncio.run(run())


def test_root_pin_decides_the_active_companion(owner_engine: Engine, client: TestClient) -> None:
    user_id = _scalar(owner_engine, "SELECT id FROM app_user ORDER BY id LIMIT 1")
    chosen = client.patch("/api/v1/companions/preference", json={"selected": "preset:herbaria"})
    assert chosen.status_code == 200, chosen.text
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO companion_account_policy (user_id, pinned_ref, pin_enabled) "
                "VALUES (:user_id, 'preset:atlas', true)"
            ),
            {"user_id": user_id},
        )
    created = client.post(CONVERSATIONS, json={"title": "Pinned"})
    assert created.status_code == 201, created.text
    detail = client.get(f"{CONVERSATIONS}/{created.json()['id']}").json()
    system = next(entry for entry in detail["entries"] if entry["kind"] == "pi.system")
    assert system["data"]["companion"]["ref"] == "preset:atlas"

    async def run() -> None:
        database = Database(TEST_DATABASE_URL)
        try:
            policy = await DbCompanionPolicyProvider(database, ttl_seconds=0).load(user_id)
            assert policy.pin_enabled and policy.pinned_ref == "preset:atlas"
        finally:
            await database.dispose()

    asyncio.run(run())


def test_the_account_cannot_write_root_settings(owner_engine: Engine, client: TestClient) -> None:
    from tests.conftest import rls_connection

    user_id = _scalar(owner_engine, "SELECT id FROM app_user ORDER BY id LIMIT 1")
    with rls_connection(owner_engine, user_id=user_id, role="user") as connection:
        assert connection.execute(text("SELECT count(*) FROM companion_preset")).scalar_one() == 6
        with pytest.raises(Exception, match=r"row-level security|permission denied"):
            connection.execute(
                text(
                    "INSERT INTO companion_account_policy (user_id, pin_enabled) "
                    "VALUES (:user_id, false)"
                ),
                {"user_id": user_id},
            )
