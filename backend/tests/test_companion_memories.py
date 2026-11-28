"""The librarian's own memories: no locks, her own tool, and who said what."""

import dataclasses
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.agent.domain.tool_catalog import TOOLS_VERSION, tool_definitions
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.companion.domain.story_domain import (
    TEMPLATE_EQUAL_ADDRESS_RULE,
    TEMPLATE_MEMORY_AGENCY,
    render_persona_section,
)
from app.module.companion.service.preset_lore_catalog import load_presets
from app.module.companion.service.seed_catalog import seed_runtime_config
from tests.conftest import UserClient

CONVERSATIONS = "/api/v1/agent/conversations"
PREFERENCE = "/api/v1/companions/preference"
SEED = seed_runtime_config()
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "d6a1f3c8e2b7_companion_weights_and_speakers.py"
)


def _new_conversation(client: TestClient) -> int:
    response = client.post(CONVERSATIONS, json={"title": "Memories"})
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


def _reply(client: TestClient, words: str) -> tuple[int, dict[str, Any]]:
    """Run one plain turn whose assistant answer is ``words``; return (conversation, entry)."""
    client.app.state.agent_chat_generator = FakeChatGenerator([text_result(words)])
    conversation_id = _new_conversation(client)
    turn = _turn(client, conversation_id, "Hello there.")
    replies = [entry for entry in turn["entries"] if entry["kind"] == "pi.assistant"]
    assert len(replies) == 1
    return conversation_id, replies[0]


def _recall(client: TestClient, **arguments: Any) -> dict[str, Any]:
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("recall_my_memories", arguments, call_id="call_recall"),
            text_result("I remember."),
        ]
    )
    turn = _turn(client, _new_conversation(client), "Do you remember?")
    results = [
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "recall_my_memories"
    ]
    assert len(results) == 1
    return results[0]


# --- memory agency ----------------------------------------------------------------


def test_memory_agency_note_is_seeded_editable_and_before_the_address_rule() -> None:
    agency = SEED.template(TEMPLATE_MEMORY_AGENCY)
    assert "Your memories are all yours" in agency
    assert "never to tell" in agency
    section = render_persona_section("You are Wren.", SEED)
    assert section.index(agency) < section.index(SEED.template(TEMPLATE_EQUAL_ADDRESS_RULE))

    edited = dataclasses.replace(
        SEED,
        templates=tuple(
            (key, "Share what you like." if key == TEMPLATE_MEMORY_AGENCY else body)
            for key, body in SEED.templates
        ),
    )
    rendered = render_persona_section("You are Wren.", edited)
    assert "Share what you like." in rendered
    assert agency not in rendered


def test_recall_tool_is_offered_only_with_a_companion(client: TestClient) -> None:
    assert "recall_my_memories" in {item["function"]["name"] for item in tool_definitions()}
    assert TOOLS_VERSION == "archive-tools-v20"

    generator = FakeChatGenerator([text_result("ok."), text_result("ok.")])
    client.app.state.agent_chat_generator = generator
    _turn(client, _new_conversation(client), "hello")
    offered = {tool["function"]["name"] for tool in generator.requests[0].tools}
    assert "recall_my_memories" in offered

    client.patch(PREFERENCE, json={"enabled": False})
    _turn(client, _new_conversation(client), "hello")
    withheld = {tool["function"]["name"] for tool in generator.requests[1].tools}
    assert "recall_my_memories" not in withheld


# --- her own memories ----------------------------------------------------------------


def test_recall_story_returns_any_weight_on_the_first_run(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """No locks: a heart memory is hers to recall from the very first conversation."""
    heart = next(item for item in load_presets()["vellum"].fragments if item.weight == "heart")
    words = " ".join(heart.text.split()[:12])
    result = _recall(client, query=words, scope="story", limit=5)
    lore = result["data"]["lore"]
    assert heart.key in {item["id"] for item in lore}
    assert {item["weight"] for item in lore} <= {"everyday", "past", "heart"}
    content = result["model"][0]["content"]
    assert '<my_memories scope="story" companion="Vellum"' in content
    assert f'id="{heart.key}" weight="heart"' in content
    assert "days_known=" in content and "conversations_together=" in content
    assert SEED.lore_guidance in content
    with owner_engine.connect() as connection:
        source = connection.execute(
            text("SELECT source FROM companion_lore_told WHERE fragment_key = :key"),
            {"key": heart.key},
        ).scalar_one()
    assert source == "recall"


# --- who said what ----------------------------------------------------------------


def test_replies_carry_their_speaker(client: TestClient) -> None:
    _, vellum = _reply(client, "The lighthouse keeps its own hours.")
    assert vellum["data"]["speaker"] == {"ref": "preset:vellum", "name": "Vellum"}
    assert vellum["speaker"] == {"ref": "preset:vellum", "name": "Vellum"}

    client.patch(PREFERENCE, json={"enabled": False})
    _, plain = _reply(client, "Here is your answer.")
    assert "speaker" not in (plain["data"] or {})
    assert plain["speaker"] is None


def test_said_scope_labels_every_librarian_and_puts_her_own_first(
    client: TestClient,
) -> None:
    _reply(client, "Vellum here: the lighthouse keeps its own hours.")
    client.patch(PREFERENCE, json={"selected": "preset:atlas"})
    _reply(client, "Atlas here: the road bends left at the old mill.")

    result = _recall(client, scope="said", limit=5)
    said = result["data"]["said"]
    labels = [(item["said_by"], item["own"]) for item in said]
    # Atlas is asking: his own words come first, labeled "you"; Vellum's carry her name.
    assert labels[0] == ("you", True)
    assert ("Vellum", False) in labels
    content = result["model"][0]["content"]
    assert 'said_by="you"' in content and 'said_by="Vellum"' in content
    assert "the lighthouse keeps its own hours" in content


def test_history_message_and_search_windows_show_the_speaker(client: TestClient) -> None:
    conversation_id, vellum = _reply(client, "Vellum here: the lighthouse keeps its own hours.")
    client.patch(PREFERENCE, json={"selected": "preset:atlas"})
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("history_message", {"message_id": vellum["id"]}, call_id="call_h"),
            text_result("Found it."),
        ]
    )
    turn = _turn(client, _new_conversation(client), "What did Vellum say?")
    result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "history_message"
    )
    assert result["data"]["speaker"] == "Vellum"
    assert result["data"]["speaker_ref"] == "preset:vellum"
    content = result["model"][0]["content"]
    assert 'role="assistant" speaker="Vellum"' in content
    assert 'role="user" speaker="the person"' in content
    assert conversation_id > 0


def test_speaker_backfill_attributes_legacy_replies(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    _, vellum = _reply(client, "An old reply from before attribution.")
    with owner_engine.begin() as connection:
        connection.execute(
            text("UPDATE agent_entry SET data = data - 'speaker' WHERE id = :id"),
            {"id": vellum["id"]},
        )
    spec = importlib.util.spec_from_file_location("speaker_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with owner_engine.begin() as connection:
        connection.execute(text(module.BACKFILL_SPEAKERS_SQL))
        data = connection.execute(
            text("SELECT data FROM agent_entry WHERE id = :id"),
            {"id": vellum["id"]},
        ).scalar_one()
    assert data["speaker"] == {"ref": "preset:vellum", "name": "Vellum"}


def test_said_never_crosses_accounts(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    _reply(client, "Owner-only words about the lighthouse.")
    other = user_client_factory().client
    _reply(other, "Other account words.")
    result = _recall(other, scope="said", limit=5)
    texts = " ".join(item["excerpt"] for item in result["data"]["said"])
    assert "Owner-only words" not in texts
    assert "Other account words." in texts
