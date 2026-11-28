"""Switching companion mid-conversation: one handoff, labeled speakers, new owner."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.module.agent.domain.companion_persona_domain import (
    COMPANION_HANDOFF_KEY,
    COMPANION_SWITCH_KEY,
    CompanionPersona,
    current_companion,
    render_handoff,
)
from app.module.agent.test.fake_chat_generator import FakeChatGenerator, text_result
from tests.conftest import UserClient

CONVERSATIONS = "/api/v1/agent/conversations"
PREFERENCE = "/api/v1/companions/preference"


def _conversation(client: TestClient, locale: str = "en") -> int:
    response = client.post(CONVERSATIONS, json={"title": "Handoff", "locale": locale})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _turn(client: TestClient, conversation_id: int, content: str, reply: str) -> dict[str, Any]:
    generator = FakeChatGenerator([text_result(reply)])
    client.app.state.agent_chat_generator = generator
    response = client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["_requests"] = generator.requests
    return body


def _entries(turn: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [entry for entry in turn["entries"] if entry["kind"] == kind]


def _sent_messages(turn: dict[str, Any]) -> list[dict[str, Any]]:
    return list(turn["_requests"][-1].messages)


def test_switch_injects_the_new_persona_once_and_stamps_the_new_speaker(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    first = _turn(client, conversation_id, "Hello.", "Vellum here.")
    first_user = _entries(first, "pi.user")[0]
    assert COMPANION_HANDOFF_KEY not in (first_user["data"] or {})

    client.patch(PREFERENCE, json={"selected": "preset:atlas"})
    second = _turn(client, conversation_id, "Who is this now?", "Atlas here.")
    second_user = _entries(second, "pi.user")[0]
    assert second_user["data"][COMPANION_SWITCH_KEY]["ref"] == "preset:atlas"
    handoff = second_user["data"][COMPANION_HANDOFF_KEY]
    assert "From here on you are Atlas" in handoff
    assert "said by Vellum" in handoff
    reply = _entries(second, "pi.assistant")[0]
    assert reply["speaker"] == {"ref": "preset:atlas", "name": "Atlas"}

    # The model sees the handoff on that user message.
    sent = _sent_messages(second)
    user_texts = [m["content"] for m in sent if m.get("role") == "user"]
    assert any("<companion_handoff>" in str(text) for text in user_texts)

    # Not repeated on the next turn; the handoff stays in history only once.
    third = _turn(client, conversation_id, "Thanks.", "You are welcome.")
    third_user = _entries(third, "pi.user")[0]
    assert COMPANION_SWITCH_KEY not in (third_user["data"] or {})
    assert _entries(third, "pi.assistant")[0]["speaker"]["ref"] == "preset:atlas"
    sent = _sent_messages(third)
    handoffs = [
        m
        for m in sent
        if m.get("role") == "user" and "<companion_handoff>" in str(m.get("content"))
    ]
    assert len(handoffs) == 1
    # Two speakers now: every earlier reply is labeled with who said it.
    assistant_texts = [str(m.get("content")) for m in sent if m.get("role") == "assistant"]
    assert any(text.startswith("[said by Vellum]") for text in assistant_texts)
    assert any(text.startswith("[said by Atlas]") for text in assistant_texts)


def test_single_speaker_history_is_not_labeled(client: TestClient) -> None:
    conversation_id = _conversation(client)
    _turn(client, conversation_id, "Hello.", "First words.")
    second = _turn(client, conversation_id, "Again.", "Second words.")
    sent = _sent_messages(second)
    assert not any(
        str(m.get("content")).startswith("[said by") for m in sent if m.get("role") == "assistant"
    )


def test_disabling_the_companion_hands_off_to_the_plain_assistant(client: TestClient) -> None:
    conversation_id = _conversation(client)
    _turn(client, conversation_id, "Hello.", "Vellum here.")
    client.patch(PREFERENCE, json={"enabled": False})
    turn = _turn(client, conversation_id, "Plain please.", "Plain answer.")
    user = _entries(turn, "pi.user")[0]
    assert user["data"][COMPANION_SWITCH_KEY]["ref"] is None
    assert "archive assistant" in user["data"][COMPANION_HANDOFF_KEY]
    assert "# Companion persona" not in user["data"][COMPANION_HANDOFF_KEY]
    assert _entries(turn, "pi.assistant")[0]["speaker"] is None
    # No persona means no recall tool.
    tools = {tool["function"]["name"] for tool in turn["_requests"][-1].tools if "function" in tool}
    assert "recall_my_memories" not in tools


def test_handoff_renders_the_persona_in_the_conversation_locale(client: TestClient) -> None:
    conversation_id = _conversation(client, locale="zh-TW")
    _turn(client, conversation_id, "你好。", "我是 Vellum。")
    client.patch(PREFERENCE, json={"selected": "preset:herbaria"})
    turn = _turn(client, conversation_id, "換人了嗎？", "我是 Herbaria。")
    handoff = _entries(turn, "pi.user")[0]["data"][COMPANION_HANDOFF_KEY]
    assert "Herbaria" in handoff
    assert any("一" <= char <= "鿿" for char in handoff)


def test_handoff_stays_inside_one_account(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    other = user_client_factory().client
    other_conversation = _conversation(other)
    _turn(other, other_conversation, "Hello.", "Vellum for the other account.")
    client.patch(PREFERENCE, json={"selected": "preset:atlas"})
    turn = _turn(other, other_conversation, "Still you?", "Still Vellum.")
    assert COMPANION_SWITCH_KEY not in (_entries(turn, "pi.user")[0]["data"] or {})
    assert _entries(turn, "pi.assistant")[0]["speaker"]["ref"] == "preset:vellum"


def test_current_companion_prefers_the_latest_switch() -> None:
    system = {"companion": {"ref": "preset:vellum", "name": "Vellum", "locale": "en"}}
    assert current_companion(system)["ref"] == "preset:vellum"
    switch = {COMPANION_SWITCH_KEY: {"ref": "preset:quill", "name": "Quill", "locale": "en"}}
    assert current_companion(system, switch)["ref"] == "preset:quill"
    off = {COMPANION_SWITCH_KEY: {"ref": None, "name": "the archive assistant", "locale": None}}
    assert current_companion(system, off) is None
    persona = CompanionPersona(ref="preset:quill", name="Quill", locale="en", content="P")
    text = render_handoff(persona, "Vellum")
    assert text.startswith("<companion_handoff>") and "\nP\n" in text


def test_after_a_switch_her_own_memories_belong_to_the_new_companion(client: TestClient) -> None:
    from app.module.agent.test.fake_chat_generator import tool_call_result

    conversation_id = _conversation(client)
    _turn(client, conversation_id, "Hello.", "Vellum here.")
    client.patch(PREFERENCE, json={"selected": "preset:atlas"})
    generator = FakeChatGenerator(
        [
            tool_call_result(
                "recall_my_memories", {"query": "maps", "scope": "story"}, call_id="c1"
            ),
            text_result("I remember the maps."),
        ]
    )
    client.app.state.agent_chat_generator = generator
    response = client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        json={"content": "Tell me about your maps."},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    result = next(
        entry
        for entry in response.json()["entries"]
        if entry["kind"] == "pi.tool-result" and entry["data"].get("tool") == "recall_my_memories"
    )
    story = result["data"].get("lore") or []
    ids = [item["id"] for item in story]
    assert ids and all(item.startswith("atlas-") for item in ids), result["data"]
