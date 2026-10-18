"""Pi-shaped agent transcript, tool loop, cache usage, and lifecycle."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import create_text

TOOL_USAGE = {
    "prompt_tokens": 21,
    "completion_tokens": 6,
    "total_tokens": 27,
    "prompt_cache_hit_tokens": 16,
    "prompt_cache_miss_tokens": 5,
}
ANSWER_USAGE = {
    "prompt_tokens": 40,
    "completion_tokens": 9,
    "total_tokens": 49,
    "prompt_cache_hit_tokens": 32,
    "prompt_cache_miss_tokens": 8,
}
SECOND_USAGE = {
    "prompt_tokens": 64,
    "completion_tokens": 7,
    "total_tokens": 71,
    "prompt_cache_hit_tokens": 56,
    "prompt_cache_miss_tokens": 8,
}
READ_USAGE = {
    "prompt_tokens": 29,
    "completion_tokens": 8,
    "total_tokens": 37,
    "prompt_cache_hit_tokens": 22,
    "prompt_cache_miss_tokens": 7,
}
PROMPT_VERSION = "archive-agent-v2"
TOOLS_VERSION = "archive-tools-v1"
PAGE_KEY = "/library"
PAGE_PATH = "/library"
PAGE_TITLE = "File Library"
PAGE_TEXT = "File Library\nWrench notes and the archive overview."
SECOND_PAGE_KEY = "/timeline"
SECOND_PAGE_TEXT = "Timeline\nA sparse chronology."
TOOL_NAMES = [
    "search_knowledge",
    "read_file",
    "read_timeline",
    "read_path",
    "read_memory",
    "save_memory",
    "search_media",
    "get_media",
    "present_resource",
]


def test_agent_entry_log_tool_loop_and_cache_usage(client: TestClient) -> None:
    created_file = create_text(
        client,
        "/agent/wrench.md",
        "The wrench is a hand tool used for chassis repair.",
        "2026-09-05T09:00:00Z",
    )
    file_id = int(created_file["id"])
    first_question = "What do we know about the wrench?"
    final_answer = f"The archive documents the wrench [file:{file_id}#1]."
    second_question = "Summarize that for the timeline."
    second_answer = f"The wrench remains a hand tool [file:{file_id}#1]."
    third_question = "What changed on the timeline?"
    third_answer = "The timeline remains sparse."

    fake = FakeChatGenerator(
        [
            tool_call_result(
                "search_knowledge",
                {"query": "wrench", "result_number": 2},
                call_id="call_search_1",
                usage=TOOL_USAGE,
            ),
            tool_call_result(
                "read_file",
                {"file_id": file_id, "chunk": 1},
                call_id="call_read_1",
                usage=READ_USAGE,
            ),
            text_result(final_answer, usage=ANSWER_USAGE),
            text_result(second_answer, usage=SECOND_USAGE),
            text_result(third_answer, usage=SECOND_USAGE),
        ]
    )
    client.app.state.agent_chat_generator = fake

    created = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Wrench research"},
    )
    assert created.status_code == 201, created.text
    conversation = created.json()
    conversation_id = conversation["id"]
    assert conversation["status"] == "active"
    assert conversation["title"] == "Wrench research"

    detail = client.get(f"/api/v1/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    system_entries = [
        entry for entry in detail.json()["entries"] if entry["kind"] == "pi.system"
    ]
    assert len(system_entries) == 1
    system_entry = system_entries[0]
    assert system_entry["model"][0]["role"] == "system"
    prompt = system_entry["model"][0]["content"]
    assert "You are DendroMatrix" in prompt
    assert "# Identity" in prompt
    assert "# Instructions" in prompt
    assert "# Context protocol" in prompt
    assert "<page_context>" in prompt

    system_data = system_entry["data"]
    assert system_data["prompt_version"] == PROMPT_VERSION
    assert system_data["tools_version"] == TOOLS_VERSION
    assert [section["name"] for section in system_data["sections"]] == [
        "identity",
        "instructions",
        "examples",
        "context_protocol",
    ]
    assert [tool["function"]["name"] for tool in system_data["tools"]] == TOOL_NAMES

    first_turn = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={
            "content": first_question,
            "request_id": "turn-1",
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert first_turn.status_code == 200, first_turn.text
    assert first_turn.headers["content-type"].startswith("application/json")
    turn = first_turn.json()
    assert turn["run"]["status"] == "completed"
    assert turn["error_code"] is None
    assert turn["answer"] == final_answer

    entries = turn["entries"]
    assert [entry["kind"] for entry in entries] == [
        "pi.page-context",
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
        "pi.assistant",
        "pi.tool-result",
        "pi.assistant",
    ]
    ids = [entry["id"] for entry in entries]
    assert ids == sorted(ids)
    assert ids[1] == turn["user_entry"]["id"]
    assert entries[0]["kind"] == "pi.page-context"
    assert entries[0]["commit_seq"] == entries[1]["commit_seq"]
    assert entries[0]["data"] == {
        "page_key": PAGE_KEY,
        "path": PAGE_PATH,
        "title": PAGE_TITLE,
        "text_chars": len(PAGE_TEXT),
        "truncated": False,
    }
    assert entries[0]["model"] == [
        {
            "role": "user",
            "content": (
                f'<page_context key="{PAGE_KEY}" path="{PAGE_PATH}" '
                f'title="{PAGE_TITLE}"><text>{PAGE_TEXT}</text></page_context>'
            ),
        }
    ]
    assert entries[1]["model"] == [{"role": "user", "content": first_question}]

    tool_call_entry = entries[2]
    tool_calls = tool_call_entry["model"][0]["tool_calls"]
    assert tool_calls[0]["id"] == "call_search_1"
    assert tool_calls[0]["function"]["name"] == "search_knowledge"

    tool_result_entry = entries[3]
    assert tool_result_entry["kind"] == "pi.tool-result"
    tool_message = tool_result_entry["model"][0]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_search_1"
    assert tool_message["name"] == "search_knowledge"
    assert tool_message["content"].startswith(
        '<tool_result name="search_knowledge" call_id="call_search_1">'
    )
    assert f'id="{file_id}"' in tool_message["content"]
    assert tool_result_entry["data"]["tool"] == "search_knowledge"
    assert tool_result_entry["data"]["status"] == "ok"
    assert tool_result_entry["data"]["arguments"] == {
        "query": "wrench",
        "result_number": 2,
    }
    file_results = tool_result_entry["data"]["file_results"]
    assert file_results[0]["viewer_url"] == f"/viewer/file/{file_id}?chunk=1"
    assert file_results[0]["excerpt"].startswith("The wrench is a hand tool")

    read_call_entry = entries[4]
    read_calls = read_call_entry["model"][0]["tool_calls"]
    assert read_calls[0]["id"] == "call_read_1"
    assert read_calls[0]["function"]["name"] == "read_file"
    read_result_entry = entries[5]
    assert read_result_entry["data"]["tool"] == "read_file"
    assert read_result_entry["data"]["viewer_url"] == (
        f"/viewer/file/{file_id}?chunk=1"
    )
    assert read_result_entry["data"]["chunks"][0]["excerpt"].startswith(
        "The wrench is a hand tool"
    )
    assert turn["tool_results"] == [tool_result_entry, read_result_entry]

    final_entry = entries[6]
    assert final_entry["model"][0]["content"] == final_answer
    assert turn["assistant_entry"] == final_entry

    assistant_entries = [
        entry for entry in entries if entry["kind"] == "pi.assistant"
    ]
    assert [entry["data"]["step"] for entry in assistant_entries] == [1, 2, 3]
    assert assistant_entries[0]["data"]["usage"] == TOOL_USAGE
    assert assistant_entries[1]["data"]["usage"] == READ_USAGE
    assert assistant_entries[2]["data"]["usage"] == ANSWER_USAGE
    assert (
        assistant_entries[0]["data"]["usage"]["prompt_cache_hit_tokens"]
        == TOOL_USAGE["prompt_cache_hit_tokens"]
    )
    assert (
        assistant_entries[2]["data"]["usage"]["prompt_cache_miss_tokens"]
        == ANSWER_USAGE["prompt_cache_miss_tokens"]
    )
    assert (
        assistant_entries[0]["data"]["cache_prefix_hash"]
        == assistant_entries[2]["data"]["cache_prefix_hash"]
    )
    assert turn["usage"] == {
        key: TOOL_USAGE[key] + READ_USAGE[key] + ANSWER_USAGE[key]
        for key in TOOL_USAGE
    }

    first_request = fake.requests[0]
    assert [message["role"] for message in first_request.messages] == [
        "system",
        "user",
        "user",
    ]
    assert first_request.messages[1]["content"].startswith(
        f'<page_context key="{PAGE_KEY}"'
    )
    assert PAGE_TEXT in first_request.messages[1]["content"]
    assert first_request.messages[2]["content"] == first_question

    first_detail = client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    ).json()
    assert first_detail["last_page_context_key"] == PAGE_KEY

    first_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"limit": 2},
    )
    assert first_page.status_code == 200
    page = first_page.json()
    assert page["total_results"] == 8
    assert page["has_more"] is True
    assert [entry["id"] for entry in page["entries"]] == [
        system_entry["id"],
        ids[0],
    ]
    cursor = page["next_after_id"]
    assert cursor == ids[0]

    second_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"after_id": cursor, "limit": 2},
    )
    assert second_page.status_code == 200
    assert [entry["id"] for entry in second_page.json()["entries"]] == [
        ids[1],
        ids[2],
    ]
    assert second_page.json()["next_after_id"] == ids[2]
    assert second_page.json()["has_more"] is True

    third_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"after_id": second_page.json()["next_after_id"], "limit": 2},
    )
    assert third_page.status_code == 200
    assert [entry["id"] for entry in third_page.json()["entries"]] == [
        ids[3],
        ids[4],
    ]
    assert third_page.json()["next_after_id"] == ids[4]
    assert third_page.json()["has_more"] is True

    fourth_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"after_id": third_page.json()["next_after_id"], "limit": 2},
    )
    assert fourth_page.status_code == 200
    assert [entry["id"] for entry in fourth_page.json()["entries"]] == [
        ids[5],
        ids[6],
    ]
    assert fourth_page.json()["has_more"] is False
    assert fourth_page.json()["next_after_id"] is None

    full_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"limit": 50},
    )
    assert full_page.status_code == 200
    all_entries = full_page.json()["entries"]
    assert [entry["id"] for entry in all_entries] == [system_entry["id"], *ids]
    assert [entry["kind"] for entry in all_entries] == [
        "pi.system",
        "pi.page-context",
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
        "pi.assistant",
        "pi.tool-result",
        "pi.assistant",
    ]

    repeated = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"limit": 50},
    )
    assert repeated.status_code == 200
    assert repeated.json()["entries"] == all_entries

    assert (
        client.patch(
            f"/api/v1/agent/conversations/{conversation_id}/entries",
            json={},
        ).status_code
        == 405
    )

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT to_regclass('public.agent_message')")
            ).scalar_one_or_none()
            is None
        )
        assert (
            connection.execute(
                text("SELECT to_regclass('public.agent_entry')")
            ).scalar_one_or_none()
            is not None
        )
    engine.dispose()

    second_turn = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={
            "content": second_question,
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert second_turn.status_code == 200, second_turn.text
    second_body = second_turn.json()
    assert second_body["run"]["status"] == "completed"
    assert second_body["answer"] == second_answer
    assert [entry["kind"] for entry in second_body["entries"]] == [
        "pi.user",
        "pi.assistant",
    ]
    assert all(
        entry["kind"] != "pi.page-context"
        for entry in second_body["entries"]
    )
    assert len(fake.requests) == 4
    same_page_request = fake.requests[3]
    same_page_context_messages = [
        message
        for message in same_page_request.messages
        if message.get("role") == "user"
        and str(message.get("content", "")).startswith("<page_context")
    ]
    assert len(same_page_context_messages) == 1
    assert same_page_context_messages[0]["content"].startswith(
        f'<page_context key="{PAGE_KEY}"'
    )
    assert PAGE_TEXT in same_page_context_messages[0]["content"]

    after_same_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    ).json()
    assert after_same_page["last_page_context_key"] == PAGE_KEY
    assert after_same_page["entries_total"] == 10

    third_turn = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={
            "content": third_question,
            "page_context": {
                "key": SECOND_PAGE_KEY,
                "path": "/timeline",
                "title": "Timeline",
                "text": SECOND_PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert third_turn.status_code == 200, third_turn.text
    third_body = third_turn.json()
    assert third_body["run"]["status"] == "completed"
    assert third_body["answer"] == third_answer
    assert [entry["kind"] for entry in third_body["entries"]] == [
        "pi.page-context",
        "pi.user",
        "pi.assistant",
    ]
    assert third_body["entries"][0]["data"]["page_key"] == SECOND_PAGE_KEY
    assert (
        third_body["entries"][0]["commit_seq"]
        == third_body["entries"][1]["commit_seq"]
    )
    assert third_body["entries"][0]["id"] < third_body["entries"][1]["id"]

    after_second_page = client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    ).json()
    assert after_second_page["last_page_context_key"] == SECOND_PAGE_KEY
    assert after_second_page["entries_total"] == 13

    assert fake.remaining == 0
    assert len(fake.requests) == 5

    final_request = fake.requests[-1]
    assert first_request.messages[0] == final_request.messages[0]
    assert first_request.tools == final_request.tools
    assert [message["role"] for message in final_request.messages] == [
        "system",
        "user",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "user",
        "assistant",
        "user",
        "user",
    ]
    final_page_context_messages = [
        message
        for message in final_request.messages
        if message.get("role") == "user"
        and str(message.get("content", "")).startswith("<page_context")
    ]
    assert len(final_page_context_messages) == 2
    assert final_page_context_messages[0]["content"].startswith(
        f'<page_context key="{PAGE_KEY}"'
    )
    assert final_page_context_messages[1]["content"].startswith(
        f'<page_context key="{SECOND_PAGE_KEY}"'
    )
    assert PAGE_TEXT in final_request.messages[1]["content"]
    assert final_request.messages[2]["content"] == first_question
    assert final_request.messages[3]["tool_calls"][0]["id"] == "call_search_1"
    assert final_request.messages[4]["tool_call_id"] == "call_search_1"
    assert final_request.messages[5]["tool_calls"][0]["id"] == "call_read_1"
    assert final_request.messages[6]["tool_call_id"] == "call_read_1"
    assert final_request.messages[7]["content"] == final_answer
    assert final_request.messages[8]["content"] == second_question
    assert final_request.messages[9]["content"] == second_answer
    assert final_request.messages[10]["content"].startswith(
        f'<page_context key="{SECOND_PAGE_KEY}"'
    )
    assert SECOND_PAGE_TEXT in final_request.messages[10]["content"]
    assert final_request.messages[11]["content"] == third_question
    assert final_request.model == conversation["model"]

    archived = client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"title": "Wrench archive", "status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None
    assert archived.json()["title"] == "Wrench archive"

    blocked = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Can this archived conversation still run?"},
        headers={"Accept": "application/json"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"] == "agent_conversation_archived"

    restored = client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"status": "active"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["archived_at"] is None

    deleted = client.delete(f"/api/v1/agent/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/agent/conversations/{conversation_id}").status_code == 404
    assert (
        client.get(
            f"/api/v1/agent/conversations/{conversation_id}/entries"
        ).status_code
        == 404
    )
    listed = client.get("/api/v1/agent/conversations")
    assert listed.status_code == 200
    assert all(
        item["id"] != conversation_id for item in listed.json()["resources"]
    )

    failing = FakeChatGenerator([])
    client.app.state.agent_chat_generator = failing
    retry_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Retry path"},
    )
    assert retry_conversation.status_code == 201, retry_conversation.text
    retry_conversation_id = retry_conversation.json()["id"]

    failed = client.post(
        f"/api/v1/agent/conversations/{retry_conversation_id}/messages",
        json={"content": "Please fail once."},
        headers={"Accept": "application/json"},
    )
    assert failed.status_code == 200, failed.text
    failed_body = failed.json()
    assert failed_body["run"]["status"] == "failed"
    assert failed_body["error_code"] == "provider_error"
    assert failed_body["assistant_entry"]["data"]["finish_reason"] == "error"
    assert failed_body["answer"] is None
    assert failing.remaining == 0

    retry_fake = FakeChatGenerator.from_texts("The retried answer [file:1#1].")
    client.app.state.agent_chat_generator = retry_fake
    retried = client.post(
        f"/api/v1/agent/conversations/{retry_conversation_id}/retry",
        json={},
        headers={"Accept": "application/json"},
    )
    assert retried.status_code == 200, retried.text
    retried_body = retried.json()
    assert retried_body["run"]["status"] == "completed"
    assert retried_body["user_entry"]["id"] == failed_body["user_entry"]["id"]
    assert retried_body["answer"] == "The retried answer [file:1#1]."
    assert [message["role"] for message in retry_fake.requests[0].messages] == [
        "system",
        "user",
    ]

    not_retryable = client.post(
        f"/api/v1/agent/conversations/{retry_conversation_id}/retry",
        json={},
        headers={"Accept": "application/json"},
    )
    assert not_retryable.status_code == 409
    assert not_retryable.json()["error"] == "agent_run_not_retryable"

    retry_entries = client.get(
        f"/api/v1/agent/conversations/{retry_conversation_id}/entries",
        params={"limit": 50},
    )
    assert retry_entries.status_code == 200
    retry_kinds = [entry["kind"] for entry in retry_entries.json()["entries"]]
    assert retry_kinds.count("pi.user") == 1
    assert retry_kinds == [
        "pi.system",
        "pi.user",
        "pi.assistant",
        "pi.assistant",
    ]
