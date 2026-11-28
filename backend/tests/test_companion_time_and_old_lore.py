"""Time-aware and web-first prompts, one guidance refresh, a "said" cutoff, and the purge."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.database.session import Database
from app.module.agent.domain.companion_persona_domain import (
    COMPANION_HANDOFF_KEY,
    COMPANION_SWITCH_KEY,
    GUIDANCE_VERSION_KEY,
)
from app.module.agent.domain.system_entry_domain import default_sections
from app.module.agent.domain.time_context_domain import current_time_block, part_of_day
from app.module.agent.domain.tool_catalog import PROMPT_VERSION, TOOLS_VERSION, tool_definitions
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
    tool_calls_result,
)
from app.module.companion.domain.seed_domain import SupersededText
from app.module.companion.domain.story_domain import TEMPLATE_PERSONA_RULES
from app.module.companion.repository.lore_purge_repository import LorePurgeRepository
from app.module.companion.service.seed_catalog import seed_runtime_config
from tests.conftest import TEST_DATABASE_URL
from tests.test_agent import ANSWER_USAGE, TOOL_USAGE, FakeWebResearchService
from tests.test_web_citations import HITS

CONVERSATIONS = "/api/v1/agent/conversations"


def _conversation(client: TestClient) -> int:
    response = client.post(CONVERSATIONS, json={"title": "Afternoon"})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _turn(client: TestClient, conversation_id: int, steps: list[Any]) -> dict[str, Any]:
    client.app.state.agent_chat_generator = FakeChatGenerator(steps)
    response = client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        json={"content": "Hello."},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _user(turn: dict[str, Any]) -> dict[str, Any]:
    return next(entry for entry in turn["entries"] if entry["kind"] == "pi.user")


# --- prompts ------------------------------------------------------------------------


def test_versions_and_web_first_guidance() -> None:
    assert PROMPT_VERSION == "archive-agent-v23"
    assert TOOLS_VERSION == "archive-tools-v22"
    sections = {section["title"]: section["body"] for section in default_sections()}
    assert "Most questions are about the world" in sections["Identity"]
    instructions = sections["Instructions"]
    assert "Search both sides first" in instructions
    assert "in the same step" in instructions
    assert "web_search with one to three" in instructions and "search_knowledge" in instructions
    assert "say so briefly and name where you looked" in instructions
    tools = {
        tool["function"]["name"]: tool["function"]["description"] for tool in tool_definitions()
    }
    assert "by default, without asking" in tools["web_search"]
    assert "alongside web_search in the same step" in tools["search_knowledge"]


def test_persona_rules_carry_the_time_rule_and_the_door() -> None:
    rules = seed_runtime_config().template(TEMPLATE_PERSONA_RULES)
    assert "current_time block" in rules
    assert 'Never say "tonight"' in rules
    assert "is who you are, not what time it is" in rules
    assert "the illusory door shows you the world" in rules


def test_time_block_names_the_part_of_day() -> None:
    assert [part_of_day(hour) for hour in (4, 5, 11, 12, 16, 17, 20, 21)] == [
        "night",
        "morning",
        "morning",
        "afternoon",
        "afternoon",
        "evening",
        "evening",
        "night",
    ]
    block = current_time_block(
        now=datetime(2026, 11, 28, 7, 55, tzinfo=UTC),
        client_timezone="Asia/Taipei",
        client_utc_offset_minutes=None,
        server_timezone="UTC",
    )
    assert "part_of_day: afternoon" in block


# --- one refresh for conversations frozen at an older prompt --------------------------


def test_old_conversation_gets_one_guidance_refresh(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    conversation_id = _conversation(client)
    first = _turn(client, conversation_id, [text_result("Hello.")])
    assert COMPANION_HANDOFF_KEY not in (_user(first)["data"] or {})

    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE agent_entry SET data = jsonb_set(data, '{prompt_version}', "
                "'\"archive-agent-v1\"') WHERE conversation_id = :id AND kind = 'pi.system'"
            ),
            {"id": conversation_id},
        )

    second = _turn(client, conversation_id, [text_result("Good afternoon.")])
    data = _user(second)["data"]
    assert "was updated after this conversation began" in data[COMPANION_HANDOFF_KEY]
    assert "current_time block" in data[COMPANION_HANDOFF_KEY]
    assert COMPANION_SWITCH_KEY not in data
    assert data[GUIDANCE_VERSION_KEY] == PROMPT_VERSION

    third = _turn(client, conversation_id, [text_result("Still here.")])
    assert COMPANION_HANDOFF_KEY not in (_user(third)["data"] or {})


def test_current_conversation_gets_no_refresh(client: TestClient) -> None:
    conversation_id = _conversation(client)
    _turn(client, conversation_id, [text_result("Hello.")])
    second = _turn(client, conversation_id, [text_result("Again.")])
    assert COMPANION_HANDOFF_KEY not in (_user(second)["data"] or {})


# --- parallel tools ---------------------------------------------------------------------


class _SlowWeb(FakeWebResearchService):
    """Counts how many searches run at once."""

    def __init__(self) -> None:
        super().__init__(search_results=HITS)
        self.active = 0
        self.peak = 0

    async def search(self, query: str, **kwargs: Any) -> Any:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.05)
            return await super().search(query, **kwargs)
        finally:
            self.active -= 1


def test_parallel_web_searches_in_one_step_run_together_and_keep_order(
    client: TestClient,
) -> None:
    web = _SlowWeb()
    client.app.state.web_research_service = web
    conversation_id = _conversation(client)
    turn = _turn(
        client,
        conversation_id,
        [
            tool_calls_result(
                [
                    ("web_search", {"query": "tea history", "objective": "Origins."}),
                    ("web_search", {"query": "tea gardens", "objective": "Gardens."}),
                ],
                call_ids=["call_a", "call_b"],
                usage=TOOL_USAGE,
            ),
            text_result("Done [web:w1].", usage=ANSWER_USAGE),
        ],
    )
    assert turn["run"]["status"] == "completed"
    assert sorted(item["query"] for item in web.searches) == ["tea gardens", "tea history"]
    assert web.peak == 2
    results = [
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "web_search"
    ]
    assert [entry["model"][0]["tool_call_id"] for entry in results] == ["call_a", "call_b"]


# --- "said" cutoff -----------------------------------------------------------------------


def _invalidate_config(client: TestClient) -> None:
    provider = getattr(client.app.state, "companion_story_config", None)
    invalidate = getattr(provider, "invalidate", None)
    if callable(invalidate):
        invalidate(None)


def test_said_recall_skips_replies_before_the_cutoff(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    _turn(client, _conversation(client), [text_result("I pressed my face into the lintel.")])
    with owner_engine.begin() as connection:
        connection.execute(text("UPDATE companion_config SET said_memory_since = now()"))
    _invalidate_config(client)
    _turn(client, _conversation(client), [text_result("The aeon-porcelain was fired blank.")])

    turn = _turn(
        client,
        _conversation(client),
        [
            tool_call_result("recall_my_memories", {"scope": "said", "limit": 5}),
            text_result("I remember."),
        ],
    )
    result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "recall_my_memories"
    )
    excerpts = " ".join(item["excerpt"] for item in result["data"]["said"])
    assert "fired blank" in excerpts
    assert "lintel" not in excerpts


# --- purge ---------------------------------------------------------------------------------


def _purge(superseded: list[SupersededText]) -> Any:
    async def run() -> Any:
        database = Database(TEST_DATABASE_URL)
        try:
            async with database.maintenance_session() as session:
                return await LorePurgeRepository(session).purge(superseded)
        finally:
            await database.dispose()

    return asyncio.run(run())


def _rows(engine: Engine, sql: str, **params: Any) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(text(sql), params).all())


def test_purge_removes_only_old_script_rows(client: TestClient, owner_engine: Engine) -> None:
    del client  # creates the account
    with owner_engine.begin() as c:
        user_id = c.execute(text("SELECT id FROM app_user ORDER BY id DESC LIMIT 1")).scalar_one()
        live = c.execute(
            text(
                "SELECT i.fragment_key, t.text FROM companion_lore_item i "
                "JOIN companion_lore_item_text t ON t.item_id = i.id AND t.locale = 'en' "
                "WHERE i.preset_id = 'vellum' AND i.retired_at IS NULL "
                "ORDER BY i.position LIMIT 1"
            )
        ).one()
        live_key, live_text = live
        c.execute(
            text(
                "INSERT INTO companion_lore_item "
                "(preset_id, fragment_key, weight, themes, refs, position, retired_at, "
                "seed_hash, admin_modified) VALUES "
                "('vellum', 'vellum-old', 'past', '[]', '[]', 900, now(), 'x', false), "
                "('vellum', 'vellum-root', 'past', '[]', '[]', 901, now(), NULL, false)"
            )
        )
        story = c.execute(
            text(
                "INSERT INTO companion_story (user_id, preset_id, locale, lore_customized) "
                "VALUES (:u, 'vellum', 'en', true) RETURNING id"
            ),
            {"u": user_id},
        ).scalar_one()
        idle = c.execute(
            text(
                "INSERT INTO companion_story (user_id, preset_id, locale, lore_customized) "
                "VALUES (:u, 'atlas', 'en', true) RETURNING id"
            ),
            {"u": user_id},
        ).scalar_one()
        atlas_key = c.execute(
            text(
                "SELECT fragment_key FROM companion_lore_item "
                "WHERE preset_id = 'atlas' AND retired_at IS NULL LIMIT 1"
            )
        ).scalar_one()
        fragments = [
            (story, "vellum-old", "old stale", False),
            (story, "vellum-gone", "edited stale", True),
            (story, live_key, "OLD SCRIPT TEXT", False),
            (story, "u-mine", "my own words", False),
            (idle, atlas_key, "old atlas copy", False),
        ]
        for position, (story_id, key, body, edited) in enumerate(fragments):
            c.execute(
                text(
                    "INSERT INTO companion_lore_fragment "
                    "(user_id, story_id, fragment_key, text, weight, position, edited) "
                    "VALUES (:u, :s, :k, :t, 'past', :p, :e)"
                ),
                {"u": user_id, "s": story_id, "k": key, "t": body, "p": position, "e": edited},
            )
        for key in ("vellum-old", live_key, "g-5"):
            c.execute(
                text(
                    "INSERT INTO companion_lore_told "
                    "(user_id, companion_ref, fragment_key, told_count, source) "
                    "VALUES (:u, 'preset:vellum', :k, 1, 'topical')"
                ),
                {"u": user_id, "k": key},
            )
        for key, action, body in (
            ("vellum-old", "replace", "x"),
            (live_key, "replace", "Old seeded text."),
            ("vellum-extra", "add", "Root's addition."),
        ):
            c.execute(
                text(
                    "INSERT INTO companion_admin_lore_override "
                    "(user_id, companion_ref, locale, fragment_key, action, text, weight, "
                    "position) VALUES (:u, 'preset:vellum', 'en', :k, :a, :t, 'past', 0)"
                ),
                {"u": user_id, "k": key, "a": action, "t": body},
            )

        for key, title, body in (
            ("g-1", "The lintel", "I pressed my face into the lintel of the First Door."),
            ("g-2", "門楣", "那天我把臉壓進門楣的木頭裡。"),
            ("g-3", "Tea in the window", "Through the door I saw your kettle steam."),
        ):
            c.execute(
                text(
                    "INSERT INTO companion_generated_story "
                    "(user_id, companion_ref, locale, fragment_key, title, text, weight, "
                    "status, source_refs) VALUES (:u, 'preset:vellum', 'en', :k, :ti, :t, "
                    "'everyday', 'published', '{}')"
                ),
                {"u": user_id, "k": key, "ti": title, "t": body},
            )

    result = _purge(
        [SupersededText("vellum", live_key, "en", "Old seeded text.")],
    )
    assert result.retired_stories == 2
    statuses = dict(
        _rows(owner_engine, "SELECT fragment_key, status FROM companion_generated_story")
    )
    assert statuses == {"g-1": "retired", "g-2": "retired", "g-3": "published"}
    assert result.retired_items == 1
    assert result.total > 0

    items = {row[0] for row in _rows(owner_engine, "SELECT fragment_key FROM companion_lore_item")}
    assert "vellum-old" not in items and "vellum-root" in items
    kept = dict(
        _rows(
            owner_engine,
            "SELECT fragment_key, text FROM companion_lore_fragment WHERE story_id = :s",
            s=story,
        )
    )
    assert set(kept) == {"vellum-gone", live_key, "u-mine"}
    assert kept[live_key] == live_text
    assert kept["u-mine"] == "my own words"
    assert not _rows(
        owner_engine, "SELECT 1 FROM companion_lore_fragment WHERE story_id = :s", s=idle
    )
    assert _rows(
        owner_engine, "SELECT lore_customized FROM companion_story WHERE id = :s", s=idle
    ) == [(False,)]
    told = {row[0] for row in _rows(owner_engine, "SELECT fragment_key FROM companion_lore_told")}
    assert told == {live_key, "g-5"}
    overrides = {
        row[0]
        for row in _rows(owner_engine, "SELECT fragment_key FROM companion_admin_lore_override")
    }
    assert overrides == {"vellum-extra"}

    # Idempotent: a second pass changes nothing.
    assert _purge([]).total == 0
