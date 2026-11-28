"""Companion personas, lore editing, recall (no locks: weights), pacing, and isolation."""

import dataclasses
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
from app.module.companion.domain.recall_domain import (
    is_self_query,
    is_semantic_embedder,
    next_untold,
    rank_self_query,
    rank_topical,
    story_moment_due,
)
from app.module.companion.domain.story_domain import (
    FRAGMENT_MAX_CHARS,
    Bond,
    LoreFragment,
    ToldRecord,
    normalize_locale,
)
from app.module.companion.service import lore_vectors
from app.module.companion.service.preset_lore_catalog import load_presets
from app.module.companion.service.seed_catalog import seed_runtime_config
from app.module.companion.service.story_config import StaticCompanionContentProvider
from tests.conftest import UserClient, rls_connection
from tests.helpers import create_memory

# The live values come from the seed; tests read them instead of constants.
SEED = seed_runtime_config()
STORY_MOMENT_EVERY_RUNS = SEED.story_moment_every_runs
TOPICAL_MIN_SIMILARITY = SEED.topical_min_similarity
PERSONA_RULES = SEED.persona_rules


def _config(**changes: Any) -> Any:
    return dataclasses.replace(SEED, **changes)


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


def _search_turn(
    client: TestClient,
    query: str,
    message: str | None = None,
) -> dict[str, Any]:
    """Run one turn (``message``, default the query) that calls search_knowledge(query)."""
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("search_knowledge", {"query": query}, call_id="call_search"),
            text_result("Here is what I found."),
        ]
    )
    conversation_id = _new_conversation(client)
    return _turn(client, conversation_id, message if message is not None else query)


def _search_once(client: TestClient, query: str, message: str | None = None) -> dict[str, Any]:
    """Run one search turn and return its only search_knowledge result."""
    results = _search_results(_search_turn(client, query, message))
    assert len(results) == 1
    return results[0]


def _user_entry(turn: dict[str, Any]) -> dict[str, Any]:
    users = [entry for entry in turn["entries"] if entry["kind"] == "pi.user"]
    assert len(users) == 1
    return users[0]


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
    assert system["data"]["prompt_version"] == "archive-agent-v21"

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
    assert client.get(f"{STORIES}/preset:nobody/persona").json()["error"] == ("companion_not_found")
    assert client.get(f"{STORIES}/not-a-ref/persona").status_code == 404


# --- lore editing ---------------------------------------------------------------


def test_lore_is_copy_on_write_and_resettable(client: TestClient) -> None:
    """The first edit copies this locale's defaults; reset discards the copy."""
    initial = client.get(f"{STORIES}/{VELLUM}/lore").json()
    assert initial["customized"] is False
    # The account never sees progress or weights; nothing is heard yet.
    assert "bond" not in initial
    assert initial["fragments"] == []
    defaults = load_presets()["vellum"].fragments

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
    assert "weight" not in first and "tier" not in first and "unlocked" not in first
    # Unheard, unedited passages stay hidden from the account.
    assert defaults[1].key not in {item["id"] for item in body["fragments"]}

    created = client.post(
        f"{STORIES}/{VELLUM}/lore",
        json={"text": "A memory the user wrote.", "weight": "heart"},
    )
    assert created.status_code == 201, created.text
    added = created.json()["fragments"][-1]
    assert added["id"].startswith("u-")
    assert added["own"] is True

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
    assert reset.json()["fragments"] == []


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
    assert (
        client.get(f"{STORIES}/{ref}/persona", params={"locale": "zh-TW"}).json()["persona"]
        == "You are Moth."
    )

    assert client.delete(f"/api/v1/companions/{companion_id}").status_code == 204
    assert client.get(f"{STORIES}/{ref}/lore").status_code == 404
    with owner_engine.connect() as connection:
        for table in ("companion_story", "companion_lore_fragment"):
            count = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert count == 0


# --- recall in search -----------------------------------------------------------


class _KeywordEmbedder:
    """A deterministic stand-in for a semantic embedder: one axis per keyword."""

    model_name = "fake-semantic"
    dimension = 5
    words = ("rain", "clock", "seed", "star")

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for value in texts:
            lowered = value.lower()
            vectors.append([1.0 if word in lowered else 0.0 for word in self.words] + [0.05])
        return vectors


@pytest.fixture()
def semantic_embedder(monkeypatch: pytest.MonkeyPatch) -> _KeywordEmbedder:
    """Give lore recall a semantic embedder without touching archive search."""
    from app.module.companion import dependencies as companion_dependencies

    embedder = _KeywordEmbedder()
    lore_vectors.clear_memory()
    monkeypatch.setattr(companion_dependencies, "_state_embedder", lambda _state: embedder)
    return embedder


def _complete_runs(client: TestClient, count: int) -> list[dict[str, Any]]:
    """Finish ``count`` plain runs in one conversation; return each user entry."""
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [text_result("ok.") for _ in range(count)]
    )
    conversation_id = _new_conversation(client)
    users: list[dict[str, Any]] = []
    for index in range(count):
        turn = _turn(client, conversation_id, f"hello {index}")
        users.extend(entry for entry in turn["entries"] if entry["kind"] == "pi.user")
    return users


def _progress(owner_engine: Engine) -> dict[str, tuple[int, str]]:
    with owner_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT fragment_key, told_count, source FROM companion_lore_told")
        ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def test_self_query_in_the_message_answers_with_untold_story(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """Asking the librarian about itself brings its own story with the message."""
    create_memory(
        client,
        "Grandmother taught me her braised pork recipe: soy sauce goes in last.",
        "2026-01-20T10:00:00+08:00",
    )
    turn = _search_turn(client, "braised pork", "Vellum, tell me about your past")
    data = _user_entry(turn)["data"]
    ids = data["companion_context_ids"]
    assert 1 <= len(ids) <= 2
    block = data["companion_context"]
    assert block.startswith('<librarian_memories moment="self"')
    assert SEED.lore_guidance in block
    assert {key: value[1] for key, value in _progress(owner_engine).items()} == {
        key: "self_query" for key in ids
    }
    # The run never repeats a fragment: anything beside the search is new.
    result = _search_results(turn)[0]
    assert set(ids).isdisjoint({item["id"] for item in result["data"].get("lore", [])})


def test_search_knowledge_never_carries_lore(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,
    owner_engine: Engine,
) -> None:
    """search_knowledge searches only the person's archive, even for a self question."""
    create_memory(client, "Rain at night on the tin roof.", "2026-01-20T10:00:00+08:00")
    about_self = _search_once(client, "Vellum, tell me about your past", "Please look it up.")
    assert "lore" not in about_self["data"]
    assert "<librarian_memories" not in about_self["model"][0]["content"]
    topical = _search_once(client, "rain at night", "Please look it up.")
    assert "lore" not in topical["data"]
    assert "<librarian_memories" not in topical["model"][0]["content"]
    assert not any(source == "topical" for _, source in _progress(owner_engine).values())


def test_topical_recall_is_semantic_only(client: TestClient) -> None:
    """The offline hash never gates lore by keywords: topical recall needs meaning."""
    create_memory(client, "It rained all evening; I stayed in.", "2026-01-20T10:00:00+08:00")
    plain = _search_once(client, "rained all evening")
    assert "lore" not in plain["data"]
    assert plain["data"]["memory_results"], "the archive memory is still found"


def test_topical_recall_has_no_locks_and_shows_weights(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,
    owner_engine: Engine,
) -> None:
    """A past (formerly locked) memory can surface on the very first run, with its weight."""
    memory = create_memory(client, "Rain at night on the tin roof.", "2026-01-20T10:00:00+08:00")
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result(
                "read_memory",
                {"memory_id": memory["memory"]["memory_id"]},
                call_id="call_read",
            ),
            text_result("Here it is."),
        ]
    )
    turn = _turn(client, _new_conversation(client), "What did I write about that night?")
    result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "read_memory"
    )
    lore = result["data"]["lore"]
    assert lore, "a rain memory of hers is near a rain memory of the person's"
    assert {item["weight"] for item in lore} <= {"everyday", "past", "heart"}
    assert "past" in {item["weight"] for item in lore}
    content = result["model"][0]["content"]
    assert 'weight="past"' in content
    assert 'days_known="0"' in content and "conversations_together=" in content
    assert all(_progress(owner_engine)[item["id"]][1] == "topical" for item in lore)
    assert semantic_embedder.calls >= 1


def test_story_moments_pace_the_arc_whatever_the_topic(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A run may open with the next untold fragment, every few completed runs."""
    users = _complete_runs(client, 1 + 1 + STORY_MOMENT_EVERY_RUNS)
    moments = [(entry["data"].get("companion_context_ids") or [None])[0] for entry in users]
    # Run 1 has no completed run yet; run 2 opens the first moment; the next
    # waits until STORY_MOMENT_EVERY_RUNS more runs have completed.
    assert moments[0] is None
    assert moments[1] == "vellum-001"
    assert all(value is None for value in moments[2:-1])
    assert moments[-1] == "vellum-002"
    block = users[1]["data"]["companion_context"]
    assert block.startswith('<librarian_memories moment="story"')
    assert "keep it for another time" in block
    progress = _progress(owner_engine)
    assert progress["vellum-001"] == (1, "story_moment")
    assert progress["vellum-002"] == (1, "story_moment")


# --- pacing (pure) --------------------------------------------------------------


def _arc(count: int) -> list[LoreFragment]:
    weights = ["everyday"] * (count // 2) + ["heart"] * (count - count // 2)
    return [
        LoreFragment(key=f"f-{index:03d}", text=f"memory {index}", themes=(), weight=weight)  # type: ignore[arg-type]
        for index, weight in enumerate(weights)
    ]


def test_a_narrow_life_still_hears_every_fragment() -> None:
    """Someone who only ever talks about one thing still hears the whole story."""
    fragments = _arc(12)
    told: dict[str, ToldRecord] = {}
    last_story_run: int | None = None
    heard: list[str] = []
    for run in range(200):
        bond = Bond(completed_runs=run, last_story_run=last_story_run)
        if story_moment_due(bond, SEED):
            upcoming = next_untold(fragments, told)
            if upcoming:
                key = upcoming[0].key
                heard.append(key)
                told[key] = ToldRecord(told_count=told.get(key, ToldRecord()).told_count + 1)
                last_story_run = run
        # A single narrow topic with no semantic match never offers lore at all.
        assert rank_topical(fragments, {}, told, limit=2, config=SEED) == []
    assert set(heard[: len(fragments)]) == {item.key for item in fragments}
    first_half = [item.key for item in fragments[: len(fragments) // 2]]
    assert heard[: len(first_half)] == first_half


def test_pacing_and_ranking_rules() -> None:
    assert not story_moment_due(Bond(completed_runs=0), SEED)
    assert story_moment_due(Bond(completed_runs=1), SEED)
    assert not story_moment_due(Bond(completed_runs=3, last_story_run=1), SEED)
    assert story_moment_due(
        Bond(completed_runs=1 + STORY_MOMENT_EVERY_RUNS, last_story_run=1), SEED
    )
    slower = _config(story_moment_every_runs=10)
    assert not story_moment_due(Bond(completed_runs=8, last_story_run=1), slower)
    never = _config(story_moment_every_runs=0)
    assert not story_moment_due(Bond(completed_runs=8), never)

    fragments = _arc(4)
    told = {"f-000": ToldRecord(told_count=2)}
    assert [item.key for item in next_untold(fragments, told, limit=2)] == [
        "f-001",
        "f-002",
    ]
    everything = {item.key: ToldRecord(told_count=1) for item in fragments}
    everything["f-003"] = ToldRecord(told_count=3)
    assert next_untold(fragments, everything)[0].key == "f-000"

    similarity = {"f-000": 0.9, "f-001": 0.85, "f-002": TOPICAL_MIN_SIMILARITY - 0.01}
    ranked = rank_topical(fragments, similarity, told, limit=2, config=SEED)
    assert [item.fragment.key for item in ranked] == ["f-001", "f-000"]
    assert rank_topical(fragments, None, told, limit=2, config=SEED) == []
    strict = _config(topical_min_similarity=0.95)
    assert rank_topical(fragments, similarity, told, limit=2, config=strict) == []

    chosen = rank_self_query(fragments, told, {"f-002": 0.5}, limit=1, config=SEED)
    assert [item.fragment.key for item in chosen] == ["f-002"]

    assert is_semantic_embedder("text-embedding-3-small", 1536)
    assert not is_semantic_embedder("apsor-hash-384", 384)
    assert not is_semantic_embedder("none", 0)


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
    client.put(f"{STORIES}/{VELLUM}/persona", json={"persona": "Owner-only voice."})
    client.post(f"{STORIES}/{VELLUM}/lore", json={"text": "Owner-only memory."})
    _complete_runs(client, 2)  # the second run opens a story moment
    companion = client.post("/api/v1/companions", json={"name": "Private"}).json()

    other = user_client_factory().client
    assert other.get(f"{STORIES}/{VELLUM}/persona").json()["is_default"] is True
    other_lore = other.get(f"{STORIES}/{VELLUM}/lore").json()
    assert other_lore["customized"] is False
    assert "bond" not in other_lore
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
    for table in (
        "companion_story",
        "companion_lore_fragment",
        "companion_bond",
        "companion_lore_told",
    ):
        with rls_connection(owner_engine, user_id=other_id, role="user") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        with rls_connection(owner_engine, user_id=owner_id, role="root") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() >= 1


# --- pure rules -----------------------------------------------------------------


def test_locale_and_selection_rules() -> None:
    assert normalize_locale(None) == "en"
    assert normalize_locale("zh_TW") == "zh-TW"
    assert normalize_locale("zh-Hant-HK") == "zh-TW"
    assert normalize_locale("zh-Hans") == "zh-CN"
    assert normalize_locale("fr-FR") == "en"
    assert is_self_query("Tell me about Atlas", ["Vellum", "Atlas"], SEED)
    assert is_self_query("說說你的過去", ["Vellum"], SEED)
    assert is_self_query("What happened at your Vespers?", [], SEED)
    assert not is_self_query("What did I eat on Tuesday?", ["Vellum"], SEED)
    # Everyday phrasing about one's own archive is not a question about the librarian.
    assert not is_self_query("What is in the archive about my trip?", ["Vellum"], SEED)
    assert not is_self_query("我的檔案館裡有外婆的食譜嗎", ["Vellum"], SEED)
    assert not is_self_query("Ask the curator of the museum", ["Vellum"], SEED)
    custom = _config(self_query_phrases=("old friend",), self_canon_terms=())
    assert is_self_query("hello old friend", [], custom)
    assert not is_self_query("tell me about your past", [], custom)


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
        # Seed files written with tiers read as weights.
        assert [fragment.weight for fragment in translated.fragments] == ["everyday", "heart"]
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
    from app.module.companion.service.preset_lore_catalog import LORE_DIRECTORY as seed_dir

    for preset_id, ids in english_ids.items():
        seed = json.loads((seed_dir / f"{preset_id}.json").read_text(encoding="utf-8"))
        assert ids == [fragment["id"] for fragment in seed["fragments"]]
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


def test_lore_vector_warmer_is_idempotent_and_semantic_only() -> None:
    """The worker embeds every shipped fragment once per model, shared via the cache."""
    import asyncio

    from app.infrastructure.embedding.hashing_embedder import HashingEmbedder

    class _Cache:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}

        async def get_json(self, key: str) -> Any:
            return self.values.get(key)

        async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
            self.values[key] = value

    cache = _Cache()
    content = StaticCompanionContentProvider()
    warmer = lore_vectors.LoreVectorWarmer(
        embedder=lambda: _KeywordEmbedder(),
        vectors=lore_vectors.LoreVectorStore(cache),
        content=lambda: content,
    )
    lore_vectors.clear_memory()
    total = len(asyncio.run(lore_vectors.preset_lore_texts(content)))
    assert asyncio.run(warmer.run_once()) == total
    assert len(cache.values) == total
    lore_vectors.clear_memory()  # another process: empty memory, warm shared cache
    assert asyncio.run(warmer.run_once()) == 0

    offline = lore_vectors.LoreVectorWarmer(
        embedder=lambda: HashingEmbedder(),
        vectors=lore_vectors.LoreVectorStore(_Cache()),
        content=lambda: content,
    )
    assert asyncio.run(offline.run_once()) == 0
