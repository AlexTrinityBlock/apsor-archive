"""Conversation-history flat index, retrieval, and message expansion."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.agent.domain.history_domain import (
    HISTORY_WINDOW_CHARS,
    HISTORY_WINDOW_OVERLAP_CHARS,
    history_windows,
)
from app.module.agent.service.history_indexer import AgentHistoryIndexer
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.knowledge.dependencies import build_history_chunk_store
from tests.conftest import UserClient


def create_conversation(client: TestClient, title: str = "History") -> int:
    response = client.post("/api/v1/agent/conversations", json={"title": title})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def send_turn(client: TestClient, conversation_id: int, content: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def entries(client: TestClient, conversation_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/agent/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return list(response.json()["entries"])


def entry_of_kind(
    client: TestClient,
    conversation_id: int,
    kind: str,
) -> dict[str, Any]:
    for entry in entries(client, conversation_id):
        if entry["kind"] == kind:
            return entry
    raise AssertionError(f"No {kind} entry in conversation {conversation_id}")


def build_indexer(client: TestClient) -> AgentHistoryIndexer:
    return AgentHistoryIndexer(
        database=client.app.state.db,
        store_factory=lambda session, user_id: build_history_chunk_store(
            client.app.state,
            session,
            user_id=user_id,
        ),
        cache=client.app.state.cache,
    )


def index_all(client: TestClient) -> int:
    """Run the indexer in the app's event loop until its cursor is drained."""
    return int(client.portal.call(build_indexer(client).drain))


def test_windows_are_256_chars_with_32_char_overlap() -> None:
    source = "".join(str(index % 10) for index in range(600))

    windows = history_windows(source)

    assert [window.content for window in windows] == [
        source[0:256],
        source[224:480],
        source[448:600],
    ]
    assert all(window.char_count <= HISTORY_WINDOW_CHARS for window in windows)
    assert windows[0].content[-HISTORY_WINDOW_OVERLAP_CHARS:] == (
        windows[1].content[:HISTORY_WINDOW_OVERLAP_CHARS]
    )
    assert windows[1].content[-HISTORY_WINDOW_OVERLAP_CHARS:] == (
        windows[2].content[:HISTORY_WINDOW_OVERLAP_CHARS]
    )


def test_indexer_writes_raw_windows_and_search_finds_history(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    conversation_id = create_conversation(client)
    unique = "zephyrine"
    user_text = unique + " " + ("The brass orrery needs calibration. " * 14)
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(client, conversation_id, user_text)

    user_entry = entry_of_kind(client, conversation_id, "pi.user")
    assistant_entry = entry_of_kind(client, conversation_id, "pi.assistant")
    indexed = index_all(client)
    assert indexed >= 2

    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT source_id, chunk_index, length(content) "
                "FROM chunk WHERE source_kind = 'history' "
                "ORDER BY source_id, chunk_index"
            )
        ).all()
    assert len(rows) >= 3
    assert {int(row[0]) for row in rows} == {int(user_entry["id"]), int(assistant_entry["id"])}
    assert max(int(row[2]) for row in rows) <= HISTORY_WINDOW_CHARS
    assert any(int(row[1]) > 1 for row in rows)

    search = client.get(
        "/api/v1/search",
        params={"query": unique, "result_number": 2},
    )
    assert search.status_code == 200, search.text
    body = search.json()
    assert body["stats"]["history_selected"] >= 1
    history_results = body["history_results"]
    assert history_results
    assert int(history_results[0]["entry_id"]) == int(user_entry["id"])
    assert unique in history_results[0]["content"]

    tool = client.get(
        "/api/v1/tools/search_knowledge",
        params={"query": unique, "result_number": 2},
    )
    assert tool.status_code == 200, tool.text
    assert f'<history_message id="{user_entry["id"]}"' in tool.text
    assert unique in tool.text


def test_search_tool_returns_bounded_history_windows(
    client: TestClient,
) -> None:
    conversation_id = create_conversation(client)
    unique = "vellumquartz"
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(
        client,
        conversation_id,
        unique + " " + ("Archive calibration note. " * 12),
    )
    user_entry = entry_of_kind(client, conversation_id, "pi.user")
    index_all(client)

    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result(
                "search_knowledge",
                {"query": unique, "result_number": 2},
            ),
            text_result("The old note is in the transcript."),
        ]
    )
    turn = send_turn(client, conversation_id, "Search for the old note.")
    tool_result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result"
        and entry["data"]["tool"] == "search_knowledge"
    )
    assert tool_result["data"]["status"] == "ok"
    assert tool_result["data"]["history_results"]
    assert int(tool_result["data"]["history_results"][0]["entry_id"]) == int(user_entry["id"])
    content = tool_result["model"][0]["content"]
    assert f'<history_message id="{user_entry["id"]}"' in content
    assert unique in content


def test_history_message_tool_expands_by_entry_id(
    client: TestClient,
) -> None:
    conversation_id = create_conversation(client)
    unique = "obsidianlark"
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(
        "The obsidian lark is filed."
    )
    send_turn(client, conversation_id, unique + " is the codeword for the project.")
    user_entry = entry_of_kind(client, conversation_id, "pi.user")
    assistant_entry = entry_of_kind(client, conversation_id, "pi.assistant")
    index_all(client)

    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result(
                "history_message",
                {"message_id": int(user_entry["id"]), "message_range": 1},
            ),
            text_result("I read the original message."),
        ]
    )
    turn = send_turn(client, conversation_id, "Expand that old message.")
    tool_result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result"
        and entry["data"]["tool"] == "history_message"
    )
    data = tool_result["data"]
    assert data["status"] == "ok"
    assert int(data["message_id"]) == int(user_entry["id"])
    assert unique in data["content"]
    assert int(assistant_entry["id"]) in {
        int(entry_id) for entry_id in data["after_ids"]
    }
    content = tool_result["model"][0]["content"]
    assert f'<history_message id="{user_entry["id"]}"' in content
    assert 'relation="after"' in content
    assert "The obsidian lark is filed." in content


def test_empty_assistant_tool_call_entry_is_not_indexed(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    conversation_id = create_conversation(client)
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("read_path", {"path": "/"}),
            text_result("The root is empty."),
        ]
    )
    send_turn(client, conversation_id, "List the root.")
    call_entry = next(
        entry
        for entry in entries(client, conversation_id)
        if entry["kind"] == "pi.assistant" and entry["model"][0].get("tool_calls")
    )
    index_all(client)

    with owner_engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM chunk "
                "WHERE source_kind = 'history' AND source_id = :entry_id"
            ),
            {"entry_id": int(call_entry["id"])},
        ).scalar_one()
    assert int(count) == 0


def test_history_search_is_owner_scoped(
    user_client_factory: Callable[..., UserClient],
) -> None:
    alice = user_client_factory("alice")
    bob = user_client_factory("bob")
    alice_conversation = create_conversation(alice.client, "Alice history")
    bob_conversation = create_conversation(bob.client, "Bob history")

    alice.client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(alice.client, alice_conversation, "alicecobalt private note")
    alice_entry = entry_of_kind(alice.client, alice_conversation, "pi.user")

    bob.client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(bob.client, bob_conversation, "bobgarnet private note")
    bob_entry = entry_of_kind(bob.client, bob_conversation, "pi.user")

    index_all(alice.client)

    alice_search = alice.client.get(
        "/api/v1/search",
        params={"query": "alicecobalt", "result_number": 2},
    )
    assert alice_search.status_code == 200, alice_search.text
    alice_ids = {
        int(item["entry_id"]) for item in alice_search.json()["history_results"]
    }
    assert int(alice_entry["id"]) in alice_ids
    assert int(bob_entry["id"]) not in alice_ids

    bob_search = bob.client.get(
        "/api/v1/search",
        params={"query": "alicecobalt", "result_number": 2},
    )
    assert bob_search.status_code == 200, bob_search.text
    assert bob_search.json()["history_results"] == []

    bob_own = bob.client.get(
        "/api/v1/search",
        params={"query": "bobgarnet", "result_number": 2},
    )
    assert bob_own.status_code == 200, bob_own.text
    assert int(bob_entry["id"]) in {
        int(item["entry_id"]) for item in bob_own.json()["history_results"]
    }


def test_deleted_conversation_is_retired_from_history_search(
    client: TestClient,
) -> None:
    conversation_id = create_conversation(client)
    unique = "saffronquill"
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(client, conversation_id, f"{unique} is a retired codeword.")
    index_all(client)

    before = client.get(
        "/api/v1/search",
        params={"query": unique, "result_number": 2},
    )
    assert before.status_code == 200, before.text
    assert before.json()["history_results"]

    deleted = client.delete(f"/api/v1/agent/conversations/{conversation_id}")
    assert deleted.status_code == 204, deleted.text
    assert client.portal.call(build_indexer(client).run_once).examined >= 0

    after = client.get(
        "/api/v1/search",
        params={"query": unique, "result_number": 2},
    )
    assert after.status_code == 200, after.text
    assert after.json()["history_results"] == []


def test_unrelated_query_does_not_fill_history_slots(client: TestClient) -> None:
    conversation_id = create_conversation(client)
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(
        client,
        conversation_id,
        "The archive notes describe local weather and a brass orrery.",
    )
    index_all(client)

    response = client.get(
        "/api/v1/search",
        params={"query": "qwertyuiop", "result_number": 2},
    )
    assert response.status_code == 200, response.text
    assert response.json()["history_results"] == []


def test_history_message_rejects_unknown_entry(client: TestClient) -> None:
    conversation_id = create_conversation(client)
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("history_message", {"message_id": 999_999}),
            text_result("That message is not available."),
        ]
    )
    turn = send_turn(client, conversation_id, "Read a missing message.")
    tool_result = next(
        entry
        for entry in turn["entries"]
        if entry["kind"] == "pi.tool-result"
        and entry["data"]["tool"] == "history_message"
    )
    assert tool_result["data"]["status"] == "error"
    assert (
        tool_result["data"]["error_code"]
        == "agent_history_message_not_found_error"
    )


def test_history_indexer_is_idempotent(client: TestClient, owner_engine: Engine) -> None:
    conversation_id = create_conversation(client)
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(client, conversation_id, "A short idempotence note.")
    first = index_all(client)
    assert first >= 2
    second = index_all(client)
    assert second == 0

    with owner_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM chunk WHERE source_kind = 'history'")
        ).scalar_one()
    assert int(count) >= 2


def read_history_message(client: TestClient, entry_id: int) -> dict[str, Any]:
    response = client.get(f"/api/v1/agent/history/{entry_id}")
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_history_message_endpoint_returns_one_owner_message(
    client: TestClient,
) -> None:
    conversation_id = create_conversation(client, "Cited history")
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(
        "You prefer orange cats."
    )
    send_turn(client, conversation_id, "I like orange cats, no memory.")

    user_entry = entry_of_kind(client, conversation_id, "pi.user")
    assistant_entry = entry_of_kind(client, conversation_id, "pi.assistant")

    user_message = read_history_message(client, int(user_entry["id"]))
    assert set(user_message) == {
        "entry_id",
        "conversation_id",
        "conversation_title",
        "role",
        "created_at",
        "content",
    }
    assert user_message["entry_id"] == int(user_entry["id"])
    assert user_message["conversation_id"] == conversation_id
    assert user_message["conversation_title"] == "Cited history"
    assert user_message["role"] == "user"
    assert user_message["content"] == "I like orange cats, no memory."
    assert user_message["created_at"]

    assistant_message = read_history_message(client, int(assistant_entry["id"]))
    assert assistant_message["entry_id"] == int(assistant_entry["id"])
    assert assistant_message["conversation_id"] == conversation_id
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == "You prefer orange cats."


def test_history_message_endpoint_is_owner_scoped(
    user_client_factory: Callable[..., UserClient],
) -> None:
    alice = user_client_factory("alice")
    bob = user_client_factory("bob")
    conversation_id = create_conversation(alice.client, "Alice history")
    alice.client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(alice.client, conversation_id, "alicecobalt private note")
    alice_entry = entry_of_kind(alice.client, conversation_id, "pi.user")

    forbidden = bob.client.get(f"/api/v1/agent/history/{alice_entry['id']}")
    assert forbidden.status_code == 404, forbidden.text
    assert forbidden.json()["error"] == "agent_history_message_not_found"

    own = read_history_message(alice.client, int(alice_entry["id"]))
    assert own["conversation_id"] == conversation_id


def test_history_message_endpoint_rejects_unknown_and_invalid_ids(
    client: TestClient,
) -> None:
    missing = client.get("/api/v1/agent/history/999999")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"] == "agent_history_message_not_found"

    invalid = client.get("/api/v1/agent/history/0")
    assert invalid.status_code == 400, invalid.text
    assert invalid.json()["error"] == "invalid_request"


def test_history_message_endpoint_hides_soft_deleted_conversation(
    client: TestClient,
) -> None:
    conversation_id = create_conversation(client, "Soon deleted")
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(client, conversation_id, "This message will be retired.")
    user_entry = entry_of_kind(client, conversation_id, "pi.user")

    deleted = client.delete(f"/api/v1/agent/conversations/{conversation_id}")
    assert deleted.status_code == 204, deleted.text

    response = client.get(f"/api/v1/agent/history/{user_entry['id']}")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "agent_history_message_not_found"


def test_history_citation_is_recorded_in_assistant_metadata(
    client: TestClient,
) -> None:
    earlier_conversation = create_conversation(client, "Earlier conversation")
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("Noted.")
    send_turn(client, earlier_conversation, "I like orange cats, no memory.")
    cited_entry = entry_of_kind(client, earlier_conversation, "pi.user")

    token = f"[history:{cited_entry['id']}]"
    asking_conversation = create_conversation(client, "Follow-up")
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(
        f'This came from an earlier conversation: "I like orange cats, no memory."{token}'
    )
    turn = send_turn(client, asking_conversation, "Where did that come from?")

    assistant_entry = turn["assistant_entry"]
    assert assistant_entry is not None
    assert token in assistant_entry["data"]["citations"]
