"""Companion personas, lore editing, lore recall in search, tiers, and isolation."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.companion.domain.story_domain import (
    FAMILIAR_UNLOCK_RUNS,
    FRAGMENT_MAX_CHARS,
    PERSONA_RULES,
    LoreFragment,
    LoreVocabulary,
    is_self_query,
    lexical_score,
    normalize_locale,
    select_fragments,
    unlocked_tiers,
)
from app.module.companion.service.preset_lore_catalog import load_presets
from tests.conftest import UserClient, rls_connection
from tests.helpers import create_memory

STORIES = "/api/v1/companions/stories"
VELLUM = "preset:vellum"
CONVERSATIONS = "/api/v1/agent/conversations"


def _system_entry(client: TestClient, conversation_id: int) -> dict[str, Any]:
    response = client.get(f"{CONVERSATIONS}/{conversation_id}")
    assert response.status_code == 200, response.text
    entries = [entry for entry in response.json()["entries"] if entry["kind"] == "pi.system"]
    assert len(entries) == 1
    return entries[0]


def _new_conversation(client: TestClient, **extra: Any) -> int:
    response = client.post(CONVERSATIONS, json={"title": "Story", **extra})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _turn(client: TestClient, conversation_id: int, content: str) -> dict[str, Any]:
    response = client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _search_results(turn: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "search_knowledge"
    ]


def _search_once(client: TestClient, query: str) -> dict[str, Any]:
    """Run one turn whose only tool call is search_knowledge(query)."""
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("search_knowledge", {"query": query}, call_id="call_search"),
            text_result("Here is what I found."),
        ]
    )
    conversation_id = _new_conversation(client)
    results = _search_results(_turn(client, conversation_id, query))
    assert len(results) == 1
    return results[0]


# --- persona -----------------------------------------------------------------


def test_default_persona_is_frozen_and_disabled_companion_has_none(
    client: TestClient,
) -> None:
    """A new conversation speaks as the flagship preset until disabled."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])
    system = _system_entry(client, _new_conversation(client))
    assert system["data"]["companion"] == {"ref": VELLUM, "name": "Vellum", "locale": "en"}
    section = system["data"]["sections"][-1]
    assert section["name"] == "companion_persona"
    assert section["title"] == "Companion persona: Vellum"
    persona = load_presets()["vellum"].persona
    # The persona comes first; the rules that outrank it follow.
    assert section["content"].index(persona) < section["content"].index(PERSONA_RULES)
    assert system["data"]["prompt_version"] == "archive-agent-v16"

    zh = _system_entry(client, _new_conversation(client, locale="zh-TW"))
    assert zh["data"]["companion"]["locale"] == "zh-TW"

    picked = client.patch("/api/v1/companions/preference", json={"selected": "preset:atlas"})
    assert picked.status_code == 200, picked.text
    atlas = _system_entry(client, _new_conversation(client))
    assert atlas["data"]["companion"]["ref"] == "preset:atlas"

    disabled = client.patch("/api/v1/companions/preference", json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    plain = _system_entry(client, _new_conversation(client))
    assert "companion" not in plain["data"]
    assert all(item["name"] != "companion_persona" for item in plain["data"]["sections"])

    invalid = client.post(CONVERSATIONS, json={"title": "Bad", "locale": "fr"})
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_request"


def test_persona_override_is_per_locale_and_resettable(client: TestClient) -> None:
    """An edit changes one locale; reset restores that locale's default."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])
    default = client.get(f"{STORIES}/{VELLUM}/persona").json()
    assert default["is_default"] is True
    assert default["persona"] == default["default_persona"]

    custom_voice = "You are Vellum, but today you speak only in short haiku."
    updated = client.put(
        f"{STORIES}/{VELLUM}/persona",
        params={"locale": "en"},
        json={"persona": custom_voice},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_default"] is False
    assert updated.json()["persona"] == custom_voice
    assert client.get(f"{STORIES}/{VELLUM}/persona", params={"locale": "zh-TW"}).json()[
        "is_default"
    ]

    system = _system_entry(client, _new_conversation(client))
    assert custom_voice in system["data"]["sections"][-1]["content"]

    reset = client.delete(f"{STORIES}/{VELLUM}/persona", params={"locale": "en"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["is_default"] is True
    assert reset.json()["persona"] == default["persona"]

    too_long = client.put(f"{STORIES}/{VELLUM}/persona", json={"persona": "x" * 4001})
    assert too_long.status_code == 400
    assert client.get(f"{STORIES}/preset:nobody/persona").json()["error"] == (
        "companion_not_found"
    )
    assert client.get(f"{STORIES}/not-a-ref/persona").status_code == 404


# --- lore editing ---------------------------------------------------------------


def test_lore_is_copy_on_write_and_resettable(client: TestClient) -> None:
    """The first edit copies this locale's defaults; reset discards the copy."""
    initial = client.get(f"{STORIES}/{VELLUM}/lore").json()
    assert initial["customized"] is False
    assert initial["bond"]["completed_runs"] == 0
    defaults = load_presets()["vellum"].fragments
    assert [item["id"] for item in initial["fragments"]] == [item.key for item in defaults]
    by_tier = {item["tier"]: item["unlocked"] for item in initial["fragments"]}
    assert by_tier == {"first": True, "familiar": False, "rare": False}
    # The editor always shows full text, even for locked tiers.
    assert all(item["text"] for item in initial["fragments"])

    target = defaults[0].key
    edited = client.patch(
        f"{STORIES}/{VELLUM}/lore/{target}",
        json={"text": "A rewritten memory.", "themes": ["Books", "books", "ink"]},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["customized"] is True
    first = next(item for item in body["fragments"] if item["id"] == target)
    assert first["text"] == "A rewritten memory."
    assert first["themes"] == ["books", "ink"]
    assert first["edited"] is True
    untouched = next(item for item in body["fragments"] if item["id"] == defaults[1].key)
    assert untouched["edited"] is False

    created = client.post(
        f"{STORIES}/{VELLUM}/lore",
        json={"text": "A memory the user wrote.", "tier": "rare"},
    )
    assert created.status_code == 201, created.text
    added = created.json()["fragments"][-1]
    assert added["id"].startswith("u-")
    assert added["tier"] == "rare"

    deleted = client.delete(f"{STORIES}/{VELLUM}/lore/{defaults[1].key}")
    assert deleted.status_code == 200, deleted.text
    assert defaults[1].key not in {item["id"] for item in deleted.json()["fragments"]}

    # Other locales still read the shipped defaults.
    other_locale = client.get(f"{STORIES}/{VELLUM}/lore", params={"locale": "zh-CN"}).json()
    assert other_locale["customized"] is False

    missing = client.patch(f"{STORIES}/{VELLUM}/lore/no-such-key", json={"text": "x"})
    assert missing.status_code == 404
    assert missing.json()["error"] == "companion_lore_not_found"
    too_long = client.post(
        f"{STORIES}/{VELLUM}/lore",
        json={"text": "x" * (FRAGMENT_MAX_CHARS + 1)},
    )
    assert too_long.status_code == 400

    reset = client.post(f"{STORIES}/{VELLUM}/lore/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["customized"] is False
    assert [item["id"] for item in reset.json()["fragments"]] == [item.key for item in defaults]


def test_custom_companion_story_and_cascade(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A custom companion owns its story; deleting it removes every story row."""
    created = client.post("/api/v1/companions", json={"name": "Moth", "gender": None})
    assert created.status_code == 201, created.text
    companion_id = created.json()["id"]
    ref = f"custom:{companion_id}"

    persona = client.get(f"{STORIES}/{ref}/persona").json()
    assert persona["is_default"] is True
    assert "Moth" in persona["persona"]
    assert client.get(f"{STORIES}/{ref}/lore").json()["fragments"] == []

    added = client.post(f"{STORIES}/{ref}/lore", json={"text": "I collect lost buttons."})
    assert added.status_code == 201, added.text
    client.put(f"{STORIES}/{ref}/persona", json={"persona": "You are Moth."})
    # Another locale falls back to what the owner wrote.
    zh = client.get(f"{STORIES}/{ref}/lore", params={"locale": "zh-TW"}).json()
    assert [item["text"] for item in zh["fragments"]] == ["I collect lost buttons."]
    assert client.get(f"{STORIES}/{ref}/persona", params={"locale": "zh-TW"}).json()[
        "persona"
    ] == "You are Moth."

    assert client.delete(f"/api/v1/companions/{companion_id}").status_code == 204
    assert client.get(f"{STORIES}/{ref}/lore").status_code == 404
    with owner_engine.connect() as connection:
        for table in ("companion_story", "companion_lore_fragment"):
            count = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert count == 0


# --- recall in search -----------------------------------------------------------


def test_search_offers_unlocked_lore_in_a_separate_block(client: TestClient) -> None:
    """Lore rides beside archive sources, never as one, and respects tiers."""
    create_memory(
        client,
        "Grandmother taught me her braised pork recipe: soy sauce goes in last.",
        "2026-01-20T10:00:00+08:00",
    )

    # A question about the librarian herself lowers the bar for first-tier lore.
    about_self = _search_once(client, "Vellum, tell me about your past and your strings")
    lore = about_self["data"]["lore"]
    assert 1 <= len(lore) <= 2
    assert {item["tier"] for item in lore} == {"first"}
    content = about_self["model"][0]["content"]
    assert "<librarian_memories>" in content
    assert "never cite it as evidence" in content
    assert content.index("<summary>") < content.index("<librarian_memories>")
    lore_ids = {item["id"] for item in lore}
    for item in about_self["data"]["memory_results"]:
        assert str(item["memory_id"]) not in lore_ids

    # Family/letters/love lore includes familiar-tier passages (for example
    # vellum-014): none may surface before enough completed runs.
    family_query = "family letters love grandmother recipe soy sauce"
    locked = _search_once(client, family_query)
    assert "familiar" not in {item["tier"] for item in locked["data"].get("lore", [])}
    assert locked["data"]["memory_results"], "the archive memory is still found"

    bond = client.get(f"{STORIES}/{VELLUM}/lore").json()["bond"]
    assert bond["completed_runs"] == 2
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [text_result("ok.") for _ in range(FAMILIAR_UNLOCK_RUNS)]
    )
    conversation_id = _new_conversation(client)
    for index in range(FAMILIAR_UNLOCK_RUNS - 2):
        _turn(client, conversation_id, f"hello {index}")
    unlocked = client.get(f"{STORIES}/{VELLUM}/lore").json()
    assert unlocked["bond"]["completed_runs"] == FAMILIAR_UNLOCK_RUNS
    assert unlocked["bond"]["familiar_unlocked_at"] is not None
    assert {item["tier"]: item["unlocked"] for item in unlocked["fragments"]}["familiar"]

    opened = _search_once(client, family_query)
    assert "familiar" in {item["tier"] for item in opened["data"]["lore"]}


def test_no_lore_without_a_frozen_companion(client: TestClient) -> None:
    """A conversation created while the companion is disabled gets no lore."""
    client.patch("/api/v1/companions/preference", json={"enabled": False})
    result = _search_once(client, "Vellum, tell me about your past")
    assert "lore" not in result["data"]
    assert "<librarian_memories>" not in result["model"][0]["content"]


# --- isolation ----------------------------------------------------------------


def test_stories_and_bonds_are_private_per_account(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
    owner_engine: Engine,
) -> None:
    """Another account never sees overrides, lore copies, or bonds."""
    client.app.state.agent_chat_generator = FakeChatGenerator([text_result("ok.")])
    client.put(f"{STORIES}/{VELLUM}/persona", json={"persona": "Owner-only voice."})
    client.post(f"{STORIES}/{VELLUM}/lore", json={"text": "Owner-only memory."})
    _turn(client, _new_conversation(client), "hi")
    companion = client.post("/api/v1/companions", json={"name": "Private"}).json()

    other = user_client_factory().client
    assert other.get(f"{STORIES}/{VELLUM}/persona").json()["is_default"] is True
    other_lore = other.get(f"{STORIES}/{VELLUM}/lore").json()
    assert other_lore["customized"] is False
    assert other_lore["bond"]["completed_runs"] == 0
    assert "Owner-only memory." not in {item["text"] for item in other_lore["fragments"]}
    foreign = other.get(f"{STORIES}/custom:{companion['id']}/lore")
    assert foreign.status_code == 404
    assert foreign.json()["error"] == "companion_not_found"

    with owner_engine.connect() as connection:
        owner_id = connection.execute(
            text("SELECT user_id FROM companion_story LIMIT 1")
        ).scalar_one()
        other_id = connection.execute(
            text("SELECT id FROM app_user WHERE id <> :owner ORDER BY id DESC LIMIT 1"),
            {"owner": owner_id},
        ).scalar_one()
    for table in ("companion_story", "companion_lore_fragment", "companion_bond"):
        with rls_connection(owner_engine, user_id=other_id, role="user") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        with rls_connection(owner_engine, user_id=owner_id, role="root") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() >= 1


# --- pure rules -----------------------------------------------------------------


def test_locale_tiers_and_selection_rules() -> None:
    assert normalize_locale(None) == "en"
    assert normalize_locale("zh_TW") == "zh-TW"
    assert normalize_locale("zh-Hant-HK") == "zh-TW"
    assert normalize_locale("zh-Hans") == "zh-CN"
    assert normalize_locale("fr-FR") == "en"
    assert unlocked_tiers(0) == {"first"}
    assert unlocked_tiers(FAMILIAR_UNLOCK_RUNS) == {"first", "familiar"}
    assert "rare" in unlocked_tiers(1000)
    assert is_self_query("Tell me about Atlas", ["Vellum", "Atlas"])
    assert not is_self_query("What did I eat on Tuesday?", ["Vellum"])

    vocabulary = LoreVocabulary(themes={"rain": ("rain", "storm")})
    rain = LoreFragment(key="rain", text="The strings grow heavy.", themes=("rain",), tier="first")
    other = LoreFragment(key="other", text="A quiet shelf.", themes=("shelves",), tier="rare")
    lexical = {
        fragment.key: lexical_score("It rained all night, a storm.", fragment, vocabulary)
        for fragment in (rain, other)
    }
    chosen = select_fragments(
        fragments=[rain, other],
        unlocked=frozenset({"first", "rare"}),
        lexical=lexical,
        semantic=None,
    )
    assert [item.fragment.key for item in chosen] == ["rain"]
    assert select_fragments(
        fragments=[rain],
        unlocked=frozenset({"familiar"}),
        lexical=lexical,
        semantic=None,
    ) == []


def test_translation_overlay_falls_back_per_item(tmp_path: Path) -> None:
    base = {
        "schema": 1,
        "id": "demo",
        "name": "Demo",
        "persona": "English persona.",
        "fragments": [
            {"id": "a", "text": "English A.", "themes": ["x"], "tier": "first"},
            {"id": "b", "text": "English B.", "themes": [], "tier": "rare"},
        ],
    }
    (tmp_path / "demo.json").write_text(json.dumps(base), encoding="utf-8")
    (tmp_path / "zh-TW").mkdir()
    (tmp_path / "zh-TW" / "demo.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "persona": "Translated persona.",
                "fragments": [{"id": "a", "text": "A2."}],
            }
        ),
        encoding="utf-8",
    )
    load_presets.cache_clear()
    try:
        translated = load_presets("zh-TW", tmp_path)["demo"]
        assert translated.persona == "Translated persona."
        assert translated.name == "Demo"
        assert [fragment.text for fragment in translated.fragments] == ["A2.", "English B."]
        assert [fragment.tier for fragment in translated.fragments] == ["first", "rare"]
        assert load_presets("zh-CN", tmp_path)["demo"].persona == "English persona."
    finally:
        load_presets.cache_clear()


def test_shipped_lore_files_are_valid() -> None:
    presets = load_presets()
    assert "vellum" in presets
    for preset in presets.values():
        assert preset.fragments
        assert len({fragment.key for fragment in preset.fragments}) == len(preset.fragments)


@pytest.mark.parametrize("locale", ["en", "zh-TW", "zh-CN"])
def test_every_locale_loads(locale: str) -> None:
    assert load_presets(locale).keys() == load_presets("en").keys()


# --- shipped lore content ----------------------------------------------------------


def test_shipped_lore_loads_in_every_locale() -> None:
    """All six presets load in en, zh-TW, and zh-CN with identical fragment ids."""
    from app.module.companion.service.preset_lore_catalog import load_presets

    english = load_presets("en")
    assert sorted(english) == ["atlas", "herbaria", "horologe", "nocturne", "quill", "vellum"]
    english_ids = {
        preset_id: [fragment.key for fragment in story.fragments]
        for preset_id, story in english.items()
    }
    assert sum(len(ids) for ids in english_ids.values()) == 183
    for locale in ("zh-TW", "zh-CN"):
        translated = load_presets(locale)
        for preset_id, story in translated.items():
            assert [fragment.key for fragment in story.fragments] == english_ids[preset_id]
            assert story.persona != english[preset_id].persona
            translated_texts = {fragment.text for fragment in story.fragments}
            assert translated_texts.isdisjoint(
                {fragment.text for fragment in english[preset_id].fragments}
            )


def test_shipped_lore_refs_point_at_canon() -> None:
    """Every fragment's refs name a canon entity; Vellum's first passage has refs."""
    import json

    from app.module.companion.service.preset_lore_catalog import LORE_DIRECTORY, load_presets

    canon = json.loads((LORE_DIRECTORY / "canon.json").read_text(encoding="utf-8"))
    entities = set(canon["entities"])
    presets = load_presets("en")
    for story in presets.values():
        for fragment in story.fragments:
            assert set(fragment.refs) <= entities
    assert presets["vellum"].fragments[0].refs


def test_vocabulary_overlays_match_chinese_queries() -> None:
    """English themes stay canonical; zh overlays add keywords for both scripts."""
    from app.module.companion.service.preset_lore_catalog import load_vocabulary

    vocabulary = load_vocabulary()
    assert {"rain", "family", "cooking"} <= vocabulary.themes_in("昨天下雨，想起外婆的食譜")
    assert {"rain", "family", "cooking"} <= vocabulary.themes_in("昨天下雨，想起外婆的菜谱")
    assert "rain" in vocabulary.themes_in("a rainy evening")
