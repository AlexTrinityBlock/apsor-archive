"""Pi-shaped agent transcript, tool loop, cache usage, and lifecycle."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.infrastructure.config.settings import Settings
from app.main import create_app
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
    tool_calls_result,
)
from tests.conftest import (
    OWNER_PASSWORD,
    OWNER_USERNAME,
    TEST_DATABASE_URL,
)
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
PROMPT_VERSION = "archive-agent-v5"
TOOLS_VERSION = "archive-tools-v2"
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
    "present_resource",
]


def test_agent_entry_log_tool_loop_and_cache_usage(
    client: TestClient,
    settings: Settings,
) -> None:
    created_file = create_text(
        client,
        "/agent/wrench.md",
        "The wrench is a hand tool used for chassis repair.",
        "2026-09-05T09:00:00Z",
    )
    file_id = int(created_file["id"])

    settings_response = client.get("/api/v1/agent/settings")
    assert settings_response.status_code == 200, settings_response.text
    settings_body = settings_response.json()
    assert settings_body["source"] == "default"
    defaults = settings_body["defaults"]
    assert settings_body["config"] == defaults
    assert defaults == {
        "max_total_tokens": 100_000,
        "compaction_threshold_tokens": 75_000,
        "context_window_tokens": 1_000_000,
        "max_steps": 24,
        "max_tool_calls_per_turn": 6,
        "max_parallel_tools": 6,
        "max_tool_result_chars": 100_000,
        "max_page_context_chars": 6_000,
        "max_compaction_summary_chars": 6_000,
        "max_compaction_last_user_chars": 4_000,
        "auto_compaction_enabled": True,
        "parallel_tools_enabled": True,
        "save_memory_requires_approval": True,
    }

    invalid_threshold = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "compaction_threshold_tokens": defaults["max_total_tokens"],
        },
    )
    assert invalid_threshold.status_code == 400
    assert invalid_threshold.json()["error"] == "invalid_request"
    assert "compaction_threshold_tokens" in invalid_threshold.json()["detail"]
    invalid_parallel = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "max_parallel_tools": defaults["max_tool_calls_per_turn"] + 1,
        },
    )
    assert invalid_parallel.status_code == 400
    assert invalid_parallel.json()["error"] == "invalid_request"

    for invalid_context_window in (7_999, 2_000_001):
        invalid_context = client.put(
            "/api/v1/agent/settings",
            json={
                **defaults,
                "context_window_tokens": invalid_context_window,
            },
        )
        assert invalid_context.status_code == 400
        assert invalid_context.json()["error"] == "invalid_request"
        assert "context_window_tokens" in invalid_context.json()["detail"]

    non_default_settings = {
        **defaults,
        "context_window_tokens": 1_500_000,
        "max_steps": 4,
        "max_tool_calls_per_turn": 4,
        "max_parallel_tools": 2,
        "max_page_context_chars": 5_000,
        "max_compaction_summary_chars": 5_000,
        "max_compaction_last_user_chars": 3_000,
        "save_memory_requires_approval": False,
    }
    stored_settings = client.put(
        "/api/v1/agent/settings",
        json=non_default_settings,
    )
    assert stored_settings.status_code == 200, stored_settings.text
    stored_body = stored_settings.json()
    assert stored_body["source"] == "database"
    assert stored_body["config"] == non_default_settings
    assert stored_body["config"]["save_memory_requires_approval"] is False
    assert stored_body["updated_at"] is not None
    persisted_settings = client.get("/api/v1/agent/settings")
    assert persisted_settings.status_code == 200
    assert persisted_settings.json()["source"] == "database"
    assert persisted_settings.json()["config"] == non_default_settings

    reset_settings = client.post("/api/v1/agent/settings/reset")
    assert reset_settings.status_code == 200, reset_settings.text
    reset_body = reset_settings.json()
    assert reset_body["source"] == "database"
    assert reset_body["config"] == defaults
    assert reset_body["config"]["save_memory_requires_approval"] is True

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
    system_entries = [entry for entry in detail.json()["entries"] if entry["kind"] == "pi.system"]
    assert len(system_entries) == 1
    system_entry = system_entries[0]
    assert system_entry["model"][0]["role"] == "system"
    prompt = system_entry["model"][0]["content"]
    assert "You are DendroMatrix" in prompt
    assert "# Identity" in prompt
    assert "# Instructions" in prompt
    assert "# Context protocol" in prompt
    assert "<page_context>" in prompt
    assert "<compaction>" in prompt

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
            "client_timezone": "Asia/Taipei",
            "client_utc_offset_minutes": 480,
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
    assert entries[1]["data"]["client_timezone"] == "Asia/Taipei"
    assert entries[1]["data"]["client_utc_offset_minutes"] == 480
    assert "<current_time>" in entries[1]["data"]["time_context"]

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
    assert read_result_entry["data"]["viewer_url"] == (f"/viewer/file/{file_id}?chunk=1")
    assert read_result_entry["data"]["chunks"][0]["excerpt"].startswith("The wrench is a hand tool")
    assert turn["tool_results"] == [tool_result_entry, read_result_entry]

    final_entry = entries[6]
    assert final_entry["model"][0]["content"] == final_answer
    assert turn["assistant_entry"] == final_entry

    assistant_entries = [entry for entry in entries if entry["kind"] == "pi.assistant"]
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
        key: TOOL_USAGE[key] + READ_USAGE[key] + ANSWER_USAGE[key] for key in TOOL_USAGE
    }

    first_request = fake.requests[0]
    assert [message["role"] for message in first_request.messages] == [
        "system",
        "user",
        "user",
    ]
    assert first_request.messages[1]["content"].startswith(f'<page_context key="{PAGE_KEY}"')
    assert PAGE_TEXT in first_request.messages[1]["content"]
    timed_question = first_request.messages[2]["content"]
    assert timed_question.startswith(first_question)
    assert "utc: " in timed_question
    assert "timezone: Asia/Taipei (UTC+08:00)" in timed_question
    assert "timezone_source: browser" in timed_question
    assert "local: " in timed_question
    assert "<current_time>" in timed_question

    first_detail = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
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
    assert all(entry["kind"] != "pi.page-context" for entry in second_body["entries"])
    assert len(fake.requests) == 4
    same_page_request = fake.requests[3]
    same_page_context_messages = [
        message
        for message in same_page_request.messages
        if message.get("role") == "user"
        and str(message.get("content", "")).startswith("<page_context")
    ]
    assert len(same_page_context_messages) == 1
    assert same_page_context_messages[0]["content"].startswith(f'<page_context key="{PAGE_KEY}"')
    assert PAGE_TEXT in same_page_context_messages[0]["content"]

    after_same_page = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
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
    assert third_body["entries"][0]["commit_seq"] == third_body["entries"][1]["commit_seq"]
    assert third_body["entries"][0]["id"] < third_body["entries"][1]["id"]

    after_second_page = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
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
    assert final_page_context_messages[0]["content"].startswith(f'<page_context key="{PAGE_KEY}"')
    assert final_page_context_messages[1]["content"].startswith(
        f'<page_context key="{SECOND_PAGE_KEY}"'
    )
    assert PAGE_TEXT in final_request.messages[1]["content"]
    assert final_request.messages[2]["content"].startswith(first_question)
    assert final_request.messages[2]["content"] == fake.requests[0].messages[2]["content"]
    assert final_request.messages[3]["tool_calls"][0]["id"] == "call_search_1"
    assert final_request.messages[4]["tool_call_id"] == "call_search_1"
    assert final_request.messages[5]["tool_calls"][0]["id"] == "call_read_1"
    assert final_request.messages[6]["tool_call_id"] == "call_read_1"
    assert final_request.messages[7]["content"] == final_answer
    assert final_request.messages[8]["content"].startswith(second_question)
    assert final_request.messages[9]["content"] == second_answer
    assert final_request.messages[10]["content"].startswith(
        f'<page_context key="{SECOND_PAGE_KEY}"'
    )
    assert SECOND_PAGE_TEXT in final_request.messages[10]["content"]
    assert final_request.messages[11]["content"].startswith(third_question)
    assert "<current_time>" in final_request.messages[11]["content"]
    assert final_request.model == conversation["model"]

    cleared = client.post(f"/api/v1/agent/conversations/{conversation_id}/clear")
    assert cleared.status_code == 200, cleared.text
    clear_entry = cleared.json()
    assert clear_entry["kind"] == "pi.reset"
    assert clear_entry["head_entry_id"] == clear_entry["id"]

    source_detail = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
    source_entries = source_detail["entries"]
    assert source_entries[-1]["id"] == clear_entry["id"]
    first_user_entry = next(entry for entry in source_entries if entry["kind"] == "pi.user")
    first_page_context = next(
        entry for entry in source_entries if entry["kind"] == "pi.page-context"
    )

    # Store one valid and one out-of-range edit to exercise fork remapping.
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE agent_entry SET edits = CAST(:edits AS jsonb) WHERE id = :entry_id"),
            {
                "edits": json.dumps(
                    [
                        {
                            "target_entry_id": first_page_context["id"],
                            "action": "omit",
                        },
                        {"target_entry_id": 999_999, "action": "omit"},
                    ]
                ),
                "entry_id": source_entries[0]["id"],
            },
        )
    engine.dispose()

    source_detail = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
    source_entries = source_detail["entries"]
    source_entry_ids = {entry["id"] for entry in source_entries}
    first_user_index = next(
        index for index, entry in enumerate(source_entries) if entry["kind"] == "pi.user"
    )
    source_updated_at = source_detail["updated_at"]
    source_last_entry_at = source_detail["last_entry_at"]

    forked_latest_response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={"title": "  Forked latest  "},
    )
    assert forked_latest_response.status_code == 201, forked_latest_response.text
    forked_latest = forked_latest_response.json()
    assert forked_latest["id"] != conversation_id
    assert forked_latest["parent_conversation_id"] == conversation_id
    assert forked_latest["fork_at_entry_id"] == clear_entry["id"]
    assert forked_latest["title"] == "Forked latest"
    assert forked_latest["status"] == "active"
    assert forked_latest["provider"] == source_detail["provider"]
    assert forked_latest["model"] == source_detail["model"]
    assert forked_latest["provider_session_id"] != source_detail["provider_session_id"]
    assert forked_latest["archived_at"] is None
    assert forked_latest["deleted_at"] is None

    forked_at_response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={"at_entry_id": first_user_entry["id"]},
    )
    assert forked_at_response.status_code == 201, forked_at_response.text
    forked_at = forked_at_response.json()
    assert forked_at["id"] != forked_latest["id"]
    assert forked_at["parent_conversation_id"] == conversation_id
    assert forked_at["fork_at_entry_id"] == first_user_entry["id"]
    assert forked_at["title"] == "Fork of Wrench research"
    assert forked_at["provider_session_id"] != source_detail["provider_session_id"]

    forked_latest_detail = client.get(f"/api/v1/agent/conversations/{forked_latest['id']}").json()
    forked_latest_entries = forked_latest_detail["entries"]
    assert len(forked_latest_entries) == len(source_entries)
    assert [entry["kind"] for entry in forked_latest_entries] == [
        entry["kind"] for entry in source_entries
    ]
    assert all(entry["id"] not in source_entry_ids for entry in forked_latest_entries)
    assert len({entry["id"] for entry in forked_latest_entries}) == len(forked_latest_entries)
    assert all(entry["by_run_id"] is None for entry in forked_latest_entries)
    assert [entry["commit_seq"] for entry in forked_latest_entries] == sorted(
        entry["commit_seq"] for entry in forked_latest_entries
    )
    for source_entry, copied_entry in zip(source_entries, forked_latest_entries, strict=True):
        assert copied_entry["kind"] == source_entry["kind"]
        assert copied_entry["model"] == source_entry["model"]
        assert copied_entry["data"] == source_entry["data"]

    copied_page_context = next(
        entry for entry in forked_latest_entries if entry["kind"] == "pi.page-context"
    )
    assert forked_latest_entries[0]["edits"] == [
        {"target_entry_id": copied_page_context["id"], "action": "omit"}
    ]
    copied_clear = forked_latest_entries[-1]
    assert copied_clear["kind"] == "pi.reset"
    assert copied_clear["head_entry_id"] == copied_clear["id"]
    assert source_entries[-1]["head_entry_id"] == source_entries[-1]["id"]

    forked_at_detail = client.get(f"/api/v1/agent/conversations/{forked_at['id']}").json()
    forked_at_entries = forked_at_detail["entries"]
    assert len(forked_at_entries) == first_user_index + 1
    assert [entry["kind"] for entry in forked_at_entries] == [
        entry["kind"] for entry in source_entries[: first_user_index + 1]
    ]
    assert forked_at_entries[-1]["kind"] == "pi.user"
    assert forked_at_entries[-1]["model"] == first_user_entry["model"]
    assert all(entry["id"] not in source_entry_ids for entry in forked_at_entries)

    fork_fake = FakeChatGenerator.from_texts("The fork continues.")
    client.app.state.agent_chat_generator = fork_fake
    fork_turn = client.post(
        f"/api/v1/agent/conversations/{forked_at['id']}/messages",
        json={"content": "Continue in the fork."},
        headers={"Accept": "application/json"},
    )
    assert fork_turn.status_code == 200, fork_turn.text
    fork_turn_body = fork_turn.json()
    assert fork_turn_body["run"]["status"] == "completed"
    assert fork_turn_body["assistant_entry"]["conversation_id"] == forked_at["id"]
    assert fork_turn_body["user_entry"]["conversation_id"] == forked_at["id"]
    assert len(fork_fake.requests) == 1
    fork_request = fork_fake.requests[0]
    assert fork_request.messages[0]["role"] == "system"
    assert "You are DendroMatrix" in fork_request.messages[0]["content"]
    assert any(
        message.get("role") == "user"
        and isinstance(message.get("content"), str)
        and message["content"].startswith(first_question)
        for message in fork_request.messages
    )
    assert fork_request.messages[-1]["content"].startswith("Continue in the fork.")

    source_after = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
    assert source_after["entries"] == source_entries
    assert source_after["updated_at"] == source_updated_at
    assert source_after["last_entry_at"] == source_last_entry_at
    assert source_after["title"] == source_detail["title"]

    cutoff_helper = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Fork cutoff helper"},
    )
    assert cutoff_helper.status_code == 201, cutoff_helper.text
    cutoff_helper_id = cutoff_helper.json()["id"]
    cutoff_helper_entry_id = client.get(f"/api/v1/agent/conversations/{cutoff_helper_id}").json()[
        "entries"
    ][0]["id"]
    foreign_cutoff = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={"at_entry_id": cutoff_helper_entry_id},
    )
    assert foreign_cutoff.status_code == 400
    assert foreign_cutoff.json()["error"] == "agent_fork_entry_invalid"
    missing_cutoff = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={"at_entry_id": 999_999},
    )
    assert missing_cutoff.status_code == 400
    assert missing_cutoff.json()["error"] == "agent_fork_entry_invalid"
    assert client.delete(f"/api/v1/agent/conversations/{cutoff_helper_id}").status_code == 204

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        busy_run_id = connection.execute(
            text(
                "INSERT INTO agent_run (conversation_id, user_entry_id, status, "
                "abort_requested, last_entry_id, started_at, created_at) "
                "VALUES (:conversation_id, :user_entry_id, 'running', false, "
                ":user_entry_id, now(), now()) RETURNING id"
            ),
            {
                "conversation_id": conversation_id,
                "user_entry_id": first_user_entry["id"],
            },
        ).scalar_one()
    busy_fork = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={},
    )
    assert busy_fork.status_code == 409
    assert busy_fork.json()["error"] == "agent_conversation_busy"
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM agent_run WHERE id = :run_id"),
            {"run_id": busy_run_id},
        )
    engine.dispose()

    long_title = "W" * 200
    renamed_source = client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"title": long_title},
    )
    assert renamed_source.status_code == 200
    clipped_fork = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={},
    )
    assert clipped_fork.status_code == 201, clipped_fork.text
    assert clipped_fork.json()["title"] == f"Fork of {long_title}"[:200]
    assert len(clipped_fork.json()["title"]) == 200
    restored_title = client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"title": "Wrench research"},
    )
    assert restored_title.status_code == 200

    archived = client.patch(
        f"/api/v1/agent/conversations/{conversation_id}",
        json={"title": "Wrench archive", "status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None
    assert archived.json()["title"] == "Wrench archive"

    archived_fork = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={},
    )
    assert archived_fork.status_code == 409
    assert archived_fork.json()["error"] == "agent_conversation_archived"

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
    assert client.get(f"/api/v1/agent/conversations/{conversation_id}/entries").status_code == 404
    missing_source_fork = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={},
    )
    assert missing_source_fork.status_code == 404
    assert missing_source_fork.json()["error"] == "agent_conversation_not_found"
    listed = client.get("/api/v1/agent/conversations")
    assert listed.status_code == 200
    assert all(item["id"] != conversation_id for item in listed.json()["resources"])

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

    parallel_fake = FakeChatGenerator(
        [
            tool_calls_result(
                [
                    ("search_knowledge", {"query": "wrench", "result_number": 1}),
                    ("read_file", {"file_id": file_id, "chunk": 1}),
                ],
                call_ids=["call_parallel_search", "call_parallel_read"],
                usage=TOOL_USAGE,
            ),
            text_result("Parallel tool batch complete.", usage=ANSWER_USAGE),
        ]
    )
    client.app.state.agent_chat_generator = parallel_fake
    parallel_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Parallel tools"},
    ).json()
    parallel_turn = client.post(
        f"/api/v1/agent/conversations/{parallel_conversation['id']}/messages",
        json={"content": "Search and read the wrench in parallel."},
        headers={"Accept": "application/json"},
    )
    assert parallel_turn.status_code == 200, parallel_turn.text
    parallel_body = parallel_turn.json()
    assert [entry["kind"] for entry in parallel_body["entries"]] == [
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
        "pi.tool-result",
        "pi.assistant",
    ]
    parallel_calls = parallel_body["entries"][1]["model"][0]["tool_calls"]
    assert [call["id"] for call in parallel_calls] == [
        "call_parallel_search",
        "call_parallel_read",
    ]
    assert [entry["model"][0]["tool_call_id"] for entry in parallel_body["tool_results"]] == [
        "call_parallel_search",
        "call_parallel_read",
    ]
    assert [entry["data"]["tool"] for entry in parallel_body["tool_results"]] == [
        "search_knowledge",
        "read_file",
    ]

    sequential_settings = {**defaults, "parallel_tools_enabled": False}
    sequential_update = client.put(
        "/api/v1/agent/settings",
        json=sequential_settings,
    )
    assert sequential_update.status_code == 200, sequential_update.text
    assert sequential_update.json()["config"]["parallel_tools_enabled"] is False

    sequential_fake = FakeChatGenerator(
        [
            tool_calls_result(
                [
                    ("search_knowledge", {"query": "wrench", "result_number": 1}),
                    ("read_file", {"file_id": file_id, "chunk": 1}),
                ],
                call_ids=["call_sequential_search", "call_sequential_read"],
                usage=TOOL_USAGE,
            ),
            text_result("Sequential tool batch complete.", usage=ANSWER_USAGE),
        ]
    )
    client.app.state.agent_chat_generator = sequential_fake
    sequential_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Sequential tools"},
    ).json()
    sequential_turn = client.post(
        f"/api/v1/agent/conversations/{sequential_conversation['id']}/messages",
        json={"content": "Search and read the wrench sequentially."},
        headers={"Accept": "application/json"},
    )
    assert sequential_turn.status_code == 200, sequential_turn.text
    sequential_body = sequential_turn.json()
    assert [entry["kind"] for entry in sequential_body["entries"]] == [
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
        "pi.tool-result",
        "pi.assistant",
    ]
    assert [entry["model"][0]["tool_call_id"] for entry in sequential_body["tool_results"]] == [
        "call_sequential_search",
        "call_sequential_read",
    ]
    assert [entry["data"]["tool"] for entry in sequential_body["tool_results"]] == [
        "search_knowledge",
        "read_file",
    ]
    assert sequential_body["answer"] == "Sequential tool batch complete."

    restore_settings = client.post("/api/v1/agent/settings/reset")
    assert restore_settings.status_code == 200, restore_settings.text
    assert restore_settings.json()["config"] == defaults

    compact_fake = FakeChatGenerator.from_texts(
        "First compact answer.",
        "Second compact answer.",
        "Third compact answer.",
        "Answer after clear.",
        "Answer with compaction disabled.",
    )
    client.app.state.agent_chat_generator = compact_fake
    compact_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Compaction path"},
    ).json()
    compact_conversation_id = compact_conversation["id"]
    first_compact_question = "First compact question."
    second_compact_question = "Second compact question."
    third_compact_question = "Third compact question."
    fourth_compact_question = "Question after clear."

    first_compact_turn = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/messages",
        json={
            "content": first_compact_question,
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert first_compact_turn.status_code == 200, first_compact_turn.text
    first_compact_body = first_compact_turn.json()
    first_compact_user_id = first_compact_body["user_entry"]["id"]

    compact_runtime = {
        **defaults,
        "max_total_tokens": 8_000,
        "compaction_threshold_tokens": 1_000,
    }
    compact_update = client.put(
        "/api/v1/agent/settings",
        json=compact_runtime,
    )
    assert compact_update.status_code == 200, compact_update.text
    assert compact_update.json()["source"] == "database"
    assert compact_update.json()["config"]["compaction_threshold_tokens"] == 1_000

    second_compact_turn = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/messages",
        json={
            "content": second_compact_question,
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert second_compact_turn.status_code == 200, second_compact_turn.text
    second_compact_body = second_compact_turn.json()
    assert [entry["kind"] for entry in second_compact_body["entries"]] == [
        "pi.compaction",
        "pi.page-context",
        "pi.user",
        "pi.assistant",
    ]
    auto_compaction = second_compact_body["entries"][0]
    auto_page_context = second_compact_body["entries"][1]
    second_compact_user = second_compact_body["entries"][2]
    assert auto_compaction["head_entry_id"] == auto_compaction["id"]
    assert auto_compaction["data"]["auto"] is True
    assert auto_compaction["data"]["reason"] == "auto_context_threshold"
    assert auto_compaction["data"]["summary_chars"] > 0
    assert auto_compaction["data"]["last_user_entry_id"] == first_compact_user_id
    assert auto_compaction["data"]["source_entry_ids"]
    assert (
        auto_compaction["commit_seq"]
        == auto_page_context["commit_seq"]
        == second_compact_user["commit_seq"]
    )
    assert (
        auto_compaction["by_run_id"]
        == auto_page_context["by_run_id"]
        == second_compact_user["by_run_id"]
    )
    auto_content = auto_compaction["model"][0]["content"]
    assert auto_compaction["model"][0]["role"] == "user"
    assert auto_content.startswith("<compaction>")
    assert first_compact_question in auto_content
    assert "Assistant:" in auto_content

    auto_request = compact_fake.requests[1]
    assert [message["role"] for message in auto_request.messages] == [
        "system",
        "user",
        "user",
        "user",
    ]
    assert auto_request.messages[1]["content"].startswith("<compaction>")
    assert first_compact_question in auto_request.messages[1]["content"]
    assert auto_page_context["model"][0]["content"].startswith("<page_context")
    assert auto_request.messages[2]["content"] == auto_page_context["model"][0]["content"]
    assert auto_request.messages[3]["content"].startswith(second_compact_question)

    manual_compaction = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/compact"
    )
    assert manual_compaction.status_code == 200, manual_compaction.text
    manual_compaction_entry = manual_compaction.json()
    assert manual_compaction_entry["kind"] == "pi.compaction"
    assert manual_compaction_entry["head_entry_id"] == manual_compaction_entry["id"]
    assert manual_compaction_entry["data"]["auto"] is False
    assert manual_compaction_entry["data"]["reason"] == "manual"
    assert manual_compaction_entry["data"]["last_user_entry_id"] == second_compact_user["id"]
    assert second_compact_question in manual_compaction_entry["model"][0]["content"]

    compacted_detail = client.get(f"/api/v1/agent/conversations/{compact_conversation_id}").json()
    assert compacted_detail["last_page_context_key"] is None

    restored_compact_settings = client.post("/api/v1/agent/settings/reset")
    assert restored_compact_settings.status_code == 200
    assert restored_compact_settings.json()["config"] == defaults

    third_compact_turn = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/messages",
        json={
            "content": third_compact_question,
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert third_compact_turn.status_code == 200, third_compact_turn.text
    third_compact_body = third_compact_turn.json()
    assert [entry["kind"] for entry in third_compact_body["entries"]] == [
        "pi.page-context",
        "pi.user",
        "pi.assistant",
    ]
    fresh_page_context = third_compact_body["entries"][0]
    assert fresh_page_context["data"]["page_key"] == PAGE_KEY
    assert fresh_page_context["id"] > manual_compaction_entry["id"]
    assert fresh_page_context["commit_seq"] == third_compact_body["entries"][1]["commit_seq"]
    assert (
        client.get(f"/api/v1/agent/conversations/{compact_conversation_id}").json()[
            "last_page_context_key"
        ]
        == PAGE_KEY
    )
    post_compaction_request = compact_fake.requests[2]
    assert post_compaction_request.messages[1]["content"].startswith("<compaction>")
    assert second_compact_question in post_compaction_request.messages[1]["content"]
    assert post_compaction_request.messages[2]["content"].startswith("<page_context")
    assert post_compaction_request.messages[3]["content"].startswith(third_compact_question)

    cleared = client.post(f"/api/v1/agent/conversations/{compact_conversation_id}/clear")
    assert cleared.status_code == 200, cleared.text
    clear_entry = cleared.json()
    assert clear_entry["kind"] == "pi.reset"
    assert clear_entry["head_entry_id"] == clear_entry["id"]
    assert clear_entry["data"] == {"reason": "manual_clear"}
    assert clear_entry["model"] == []
    cleared_detail = client.get(f"/api/v1/agent/conversations/{compact_conversation_id}").json()
    assert cleared_detail["last_page_context_key"] is None

    fourth_compact_turn = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/messages",
        json={
            "content": fourth_compact_question,
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert fourth_compact_turn.status_code == 200, fourth_compact_turn.text
    fourth_compact_body = fourth_compact_turn.json()
    assert [entry["kind"] for entry in fourth_compact_body["entries"]] == [
        "pi.page-context",
        "pi.user",
        "pi.assistant",
    ]
    assert fourth_compact_body["entries"][0]["id"] > clear_entry["id"]
    assert fourth_compact_body["entries"][0]["data"]["page_key"] == PAGE_KEY
    after_clear_request = compact_fake.requests[3]
    assert [message["role"] for message in after_clear_request.messages] == [
        "system",
        "user",
        "user",
    ]
    assert after_clear_request.messages[1]["content"].startswith("<page_context")
    assert after_clear_request.messages[2]["content"].startswith(fourth_compact_question)
    history = [
        message.get("content")
        for message in after_clear_request.messages[1:]
        if isinstance(message.get("content"), str)
    ]
    assert all("First compact answer." not in item for item in history)

    disabled_compaction_settings = {
        **defaults,
        "max_total_tokens": 8_000,
        "compaction_threshold_tokens": 1_000,
        "auto_compaction_enabled": False,
    }
    disabled_update = client.put(
        "/api/v1/agent/settings",
        json=disabled_compaction_settings,
    )
    assert disabled_update.status_code == 200, disabled_update.text
    assert disabled_update.json()["config"]["auto_compaction_enabled"] is False

    disabled_turn = client.post(
        f"/api/v1/agent/conversations/{compact_conversation_id}/messages",
        json={
            "content": "Do not compact this turn.",
            "page_context": {
                "key": PAGE_KEY,
                "path": PAGE_PATH,
                "title": PAGE_TITLE,
                "text": PAGE_TEXT,
            },
        },
        headers={"Accept": "application/json"},
    )
    assert disabled_turn.status_code == 200, disabled_turn.text
    disabled_body = disabled_turn.json()
    assert [entry["kind"] for entry in disabled_body["entries"]] == [
        "pi.user",
        "pi.assistant",
    ]
    assert disabled_body["answer"] == "Answer with compaction disabled."

    final_reset = client.post("/api/v1/agent/settings/reset")
    assert final_reset.status_code == 200, final_reset.text
    assert final_reset.json()["config"] == defaults

    # Saved-question library: capture, ask, edit/reset, failure, pagination,
    # deletion, and FK SET NULL when the source conversation row is removed.
    saved_first_question = (
        "What do we know about the wrench and the chassis repair notes "
        "that were captured in the archive for later review?"
    )
    saved_second_question = "How should I recall a stored memory?"
    saved_third_question = "Which image files mention the wrench?"
    saved_answer = f"The saved archive answer cites the wrench [file:{file_id}#1]."
    saved_fake = FakeChatGenerator.from_texts(saved_answer)
    client.app.state.agent_chat_generator = saved_fake

    invalid_saved_question = client.post(
        "/api/v1/agent/questions",
        json={"question": "   "},
    )
    assert invalid_saved_question.status_code == 400
    assert invalid_saved_question.json()["error"] == "invalid_request"
    client_supplied_answer = client.post(
        "/api/v1/agent/questions",
        json={"question": "Do not accept this answer.", "answer": "client answer"},
    )
    assert client_supplied_answer.status_code == 400
    assert client_supplied_answer.json()["error"] == "invalid_request"

    created_saved_first = client.post(
        "/api/v1/agent/questions",
        json={"question": f"  {saved_first_question}  "},
    )
    assert created_saved_first.status_code == 201, created_saved_first.text
    saved_first = created_saved_first.json()
    saved_first_id = saved_first["id"]
    assert saved_first["question"] == saved_first_question
    assert saved_first["answer"] is None
    assert saved_first["citations"] == []
    assert saved_first["conversation_id"] is None
    assert saved_first["run_status"] is None
    assert saved_first["error_code"] is None
    assert saved_first["error_detail"] is None
    assert saved_first["last_asked_at"] is None
    assert saved_first["updated_at"] >= saved_first["created_at"]

    created_saved_second = client.post(
        "/api/v1/agent/questions",
        json={"question": saved_second_question},
    )
    assert created_saved_second.status_code == 201, created_saved_second.text
    saved_second_id = created_saved_second.json()["id"]

    created_saved_third = client.post(
        "/api/v1/agent/questions",
        json={"question": saved_third_question},
    )
    assert created_saved_third.status_code == 201, created_saved_third.text
    saved_third_id = created_saved_third.json()["id"]

    saved_page_one = client.get(
        "/api/v1/agent/questions",
        params={"limit": 2, "offset": 0},
    )
    assert saved_page_one.status_code == 200, saved_page_one.text
    saved_page_one_body = saved_page_one.json()
    assert saved_page_one_body["total"] == 3
    assert saved_page_one_body["limit"] == 2
    assert saved_page_one_body["offset"] == 0
    assert [item["id"] for item in saved_page_one_body["resources"]] == [
        saved_third_id,
        saved_second_id,
    ]
    assert all(item["answer"] is None for item in saved_page_one_body["resources"])

    saved_page_two = client.get(
        "/api/v1/agent/questions",
        params={"limit": 2, "offset": 2},
    )
    assert saved_page_two.status_code == 200
    assert saved_page_two.json()["total"] == 3
    assert saved_page_two.json()["limit"] == 2
    assert saved_page_two.json()["offset"] == 2
    assert [item["id"] for item in saved_page_two.json()["resources"]] == [saved_first_id]

    saved_empty_page = client.get(
        "/api/v1/agent/questions",
        params={"limit": 50, "offset": 10},
    )
    assert saved_empty_page.status_code == 200
    assert saved_empty_page.json()["total"] == 3
    assert saved_empty_page.json()["resources"] == []

    conversations_before_ask = client.get(
        "/api/v1/agent/conversations",
        params={"limit": 100},
    ).json()
    asked_saved_first = client.post(f"/api/v1/agent/questions/{saved_first_id}/ask")
    assert asked_saved_first.status_code == 200, asked_saved_first.text
    asked_first = asked_saved_first.json()
    assert asked_first["id"] == saved_first_id
    assert asked_first["question"] == saved_first_question
    assert asked_first["answer"] == saved_answer
    assert asked_first["citations"] == [f"[file:{file_id}#1]"]
    assert asked_first["conversation_id"] is not None
    assert asked_first["run_status"] == "completed"
    assert asked_first["error_code"] is None
    assert asked_first["error_detail"] is None
    assert asked_first["last_asked_at"] is not None
    assert saved_fake.remaining == 0

    conversations_after_ask = client.get(
        "/api/v1/agent/conversations",
        params={"limit": 100},
    ).json()
    assert conversations_after_ask["total_results"] == conversations_before_ask["total_results"] + 1
    asked_conversation_id = asked_first["conversation_id"]
    asked_conversation = client.get(f"/api/v1/agent/conversations/{asked_conversation_id}")
    assert asked_conversation.status_code == 200
    assert asked_conversation.json()["title"] == saved_first_question[:80].strip()
    asked_conversation_entries = client.get(
        f"/api/v1/agent/conversations/{asked_conversation_id}/entries",
        params={"limit": 50},
    ).json()["entries"]
    asked_user_entries = [
        entry for entry in asked_conversation_entries if entry["kind"] == "pi.user"
    ]
    assert [entry["model"][0]["content"] for entry in asked_user_entries] == [saved_first_question]
    assert saved_fake.requests[0].messages[-1]["content"].startswith(saved_first_question)

    after_ask_library = client.get(
        "/api/v1/agent/questions",
        params={"limit": 100},
    ).json()
    assert after_ask_library["total"] == 3
    assert sum(1 for item in after_ask_library["resources"] if item["id"] == saved_first_id) == 1
    stored_first = next(
        item for item in after_ask_library["resources"] if item["id"] == saved_first_id
    )
    assert stored_first["answer"] == saved_answer
    assert stored_first["citations"] == [f"[file:{file_id}#1]"]

    edited_saved_first = client.patch(
        f"/api/v1/agent/questions/{saved_first_id}",
        json={"question": "  Edited wrench question.  "},
    )
    assert edited_saved_first.status_code == 200, edited_saved_first.text
    edited_first = edited_saved_first.json()
    assert edited_first["question"] == "Edited wrench question."
    assert edited_first["answer"] is None
    assert edited_first["citations"] == []
    assert edited_first["conversation_id"] is None
    assert edited_first["run_status"] is None
    assert edited_first["error_code"] is None
    assert edited_first["error_detail"] is None
    assert edited_first["last_asked_at"] is None

    client.app.state.agent_chat_generator = FakeChatGenerator([])
    failed_saved_ask = client.post(f"/api/v1/agent/questions/{saved_second_id}/ask")
    assert failed_saved_ask.status_code == 200, failed_saved_ask.text
    failed_saved = failed_saved_ask.json()
    assert failed_saved["id"] == saved_second_id
    assert failed_saved["question"] == saved_second_question
    assert failed_saved["answer"] is None
    assert failed_saved["citations"] == []
    assert failed_saved["conversation_id"] is not None
    assert failed_saved["run_status"] == "failed"
    assert failed_saved["error_code"] == "provider_error"
    assert failed_saved["error_detail"]
    assert failed_saved["last_asked_at"] is not None

    after_failure_library = client.get(
        "/api/v1/agent/questions",
        params={"limit": 100},
    ).json()
    assert after_failure_library["total"] == 3
    retained_failure = next(
        item for item in after_failure_library["resources"] if item["id"] == saved_second_id
    )
    assert retained_failure["question"] == saved_second_question
    assert retained_failure["run_status"] == "failed"
    assert retained_failure["error_detail"]

    saved_third_answer = "The wrench appears in an image file [file:9#2]."
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(saved_third_answer)
    asked_saved_third = client.post(f"/api/v1/agent/questions/{saved_third_id}/ask")
    assert asked_saved_third.status_code == 200, asked_saved_third.text
    asked_third = asked_saved_third.json()
    assert asked_third["answer"] == saved_third_answer
    assert asked_third["citations"] == ["[file:9#2]"]
    assert asked_third["conversation_id"] is not None
    doomed_conversation_id = asked_third["conversation_id"]

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM agent_run WHERE conversation_id = :conversation_id"),
            {"conversation_id": doomed_conversation_id},
        )
        connection.execute(
            text("DELETE FROM agent_entry WHERE conversation_id = :conversation_id"),
            {"conversation_id": doomed_conversation_id},
        )
        connection.execute(
            text("DELETE FROM agent_conversation WHERE id = :conversation_id"),
            {"conversation_id": doomed_conversation_id},
        )
    engine.dispose()

    preserved_library = client.get(
        "/api/v1/agent/questions",
        params={"limit": 100},
    ).json()
    preserved_third = next(
        item for item in preserved_library["resources"] if item["id"] == saved_third_id
    )
    assert preserved_third["conversation_id"] is None
    assert preserved_third["question"] == saved_third_question
    assert preserved_third["answer"] == saved_third_answer
    assert preserved_third["citations"] == ["[file:9#2]"]
    assert preserved_library["total"] == 3

    missing_question_id = 999_999
    missing_update = client.patch(
        f"/api/v1/agent/questions/{missing_question_id}",
        json={"question": "Missing question"},
    )
    assert missing_update.status_code == 404
    assert missing_update.json()["error"] == "saved_question_not_found"
    missing_ask = client.post(f"/api/v1/agent/questions/{missing_question_id}/ask")
    assert missing_ask.status_code == 404
    assert missing_ask.json()["error"] == "saved_question_not_found"
    missing_delete = client.delete(f"/api/v1/agent/questions/{missing_question_id}")
    assert missing_delete.status_code == 404
    assert missing_delete.json()["error"] == "saved_question_not_found"

    deleted_saved_second = client.delete(f"/api/v1/agent/questions/{saved_second_id}")
    assert deleted_saved_second.status_code == 204
    deleted_saved_second_again = client.delete(f"/api/v1/agent/questions/{saved_second_id}")
    assert deleted_saved_second_again.status_code == 404
    after_delete_library = client.get(
        "/api/v1/agent/questions",
        params={"limit": 100},
    ).json()
    assert after_delete_library["total"] == 2
    assert all(item["id"] != saved_second_id for item in after_delete_library["resources"])

    # ------------------------------------------------------------------
    # save_memory requires a durable human approval. The model-supplied
    # user_confirmed flag is deliberately true here and must not bypass it.
    # ------------------------------------------------------------------
    def memory_count() -> int:
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as connection:
            total = connection.execute(text("SELECT count(*) FROM memory")).scalar_one()
        engine.dispose()
        return int(total)

    approval_content = "The wrench approval memory."
    approval_fake = FakeChatGenerator(
        [
            tool_calls_result(
                [
                    ("search_knowledge", {"query": "wrench", "result_number": 1}),
                    (
                        "save_memory",
                        {
                            "content": approval_content,
                            "supersedes": [],
                            "user_confirmed": True,
                        },
                    ),
                ],
                call_ids=["call_approval_search", "call_approval_memory"],
                usage=TOOL_USAGE,
            ),
            text_result("The approved memory is now archived.", usage=ANSWER_USAGE),
        ]
    )
    client.app.state.agent_chat_generator = approval_fake
    approval_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Memory approval"},
    ).json()
    approval_conversation_id = approval_conversation["id"]

    before_approval_memories = memory_count()
    waiting_turn = client.post(
        f"/api/v1/agent/conversations/{approval_conversation_id}/messages",
        json={"content": "Save the wrench note."},
        headers={"Accept": "application/json"},
    )
    assert waiting_turn.status_code == 200, waiting_turn.text
    waiting_body = waiting_turn.json()
    assert waiting_body["run"]["status"] == "waiting"
    assert waiting_body["answer"] is None
    assert [entry["kind"] for entry in waiting_body["entries"]] == [
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
    ]
    assert waiting_body["tool_results"][0]["data"]["tool"] == "search_knowledge"
    assert len(waiting_body["pending_approvals"]) == 1
    approval = waiting_body["pending_approvals"][0]
    approval_id = approval["id"]
    assert approval["conversation_id"] == approval_conversation_id
    assert approval["run_id"] == waiting_body["run"]["id"]
    assert approval["tool_call_id"] == "call_approval_memory"
    assert approval["tool_name"] == "save_memory"
    assert approval["status"] == "pending"
    assert approval["arguments"]["user_confirmed"] is True
    assert approval["preview"]["content"] == approval_content
    assert approval["preview"]["content_chars"] == len(approval_content)
    assert approval["preview"]["supersedes"] == []
    assert memory_count() == before_approval_memories

    # The transcript stays readable: the assistant tool call is not dropped.
    reloaded_detail = client.get(f"/api/v1/agent/conversations/{approval_conversation_id}")
    assert reloaded_detail.status_code == 200
    reloaded_entries = reloaded_detail.json()["entries"]
    assert [entry["kind"] for entry in reloaded_entries] == [
        "pi.system",
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
    ]
    assert reloaded_entries[-2]["model"][0]["tool_calls"][0]["id"] == ("call_approval_search")
    assert [call["id"] for call in reloaded_entries[-2]["model"][0]["tool_calls"]] == [
        "call_approval_search",
        "call_approval_memory",
    ]
    pending_list = client.get(f"/api/v1/agent/conversations/{approval_conversation_id}/approvals")
    assert pending_list.status_code == 200, pending_list.text
    assert [item["id"] for item in pending_list.json()["resources"]] == [approval_id]

    # A fresh app lifespan (API restart) keeps a waiting run with a valid
    # pending approval resumable.
    with TestClient(create_app(settings)) as restarted_client:
        login = restarted_client.post(
            "/api/v1/auth/login",
            json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD},
        )
        assert login.status_code == 200, login.text
        restarted_approvals = restarted_client.get(
            f"/api/v1/agent/conversations/{approval_conversation_id}/approvals"
        )
        assert restarted_approvals.status_code == 200, restarted_approvals.text
        assert [item["id"] for item in restarted_approvals.json()["resources"]] == [approval_id]
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as connection:
            restarted_run = connection.execute(
                text("SELECT status FROM agent_run WHERE id = :run_id"),
                {"run_id": waiting_body["run"]["id"]},
            ).scalar_one()
        engine.dispose()
        assert restarted_run == "waiting"

    approved_turn = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Accept": "application/json"},
    )
    assert approved_turn.status_code == 200, approved_turn.text
    approved_body = approved_turn.json()
    assert approved_body["run"]["status"] == "completed"
    assert approved_body["answer"] == "The approved memory is now archived."
    approved_results = [
        entry for entry in approved_body["tool_results"] if entry["data"]["tool"] == "save_memory"
    ]
    assert len(approved_results) == 1
    assert approved_results[0]["data"]["status"] == "ok"
    assert approved_results[0]["data"]["memory_id"] > 0
    assert approved_results[0]["model"][0]["tool_call_id"] == "call_approval_memory"
    assert memory_count() == before_approval_memories + 1
    approved_memories = memory_count()

    duplicate_approve = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Accept": "application/json"},
    )
    assert duplicate_approve.status_code == 409
    assert duplicate_approve.json()["error"] == "agent_approval_not_pending"
    assert memory_count() == approved_memories

    # Rejecting appends a clear tool result and resumes without a write.
    reject_fake = FakeChatGenerator(
        [
            tool_call_result(
                "save_memory",
                {
                    "content": "This memory must be rejected.",
                    "user_confirmed": True,
                },
                call_id="call_reject_memory",
            ),
            text_result("Understood. The memory was not saved."),
        ]
    )
    client.app.state.agent_chat_generator = reject_fake
    reject_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Memory rejection"},
    ).json()
    reject_waiting = client.post(
        f"/api/v1/agent/conversations/{reject_conversation['id']}/messages",
        json={"content": "Save this note."},
        headers={"Accept": "application/json"},
    )
    assert reject_waiting.status_code == 200, reject_waiting.text
    reject_body = reject_waiting.json()
    assert reject_body["run"]["status"] == "waiting"
    reject_approval_id = reject_body["pending_approvals"][0]["id"]

    rejected_turn = client.post(
        f"/api/v1/agent/approvals/{reject_approval_id}/reject",
        headers={"Accept": "application/json"},
    )
    assert rejected_turn.status_code == 200, rejected_turn.text
    rejected_body = rejected_turn.json()
    assert rejected_body["run"]["status"] == "completed"
    assert rejected_body["answer"] == "Understood. The memory was not saved."
    rejected_results = [
        entry for entry in rejected_body["tool_results"] if entry["data"]["tool"] == "save_memory"
    ]
    assert len(rejected_results) == 1
    assert rejected_results[0]["data"]["status"] == "error"
    assert rejected_results[0]["data"]["error_code"] == "memory_rejected"
    assert "No memory was saved" in rejected_results[0]["model"][0]["content"]
    assert memory_count() == approved_memories
    duplicate_reject = client.post(
        f"/api/v1/agent/approvals/{reject_approval_id}/reject",
        headers={"Accept": "application/json"},
    )
    assert duplicate_reject.status_code == 409
    assert duplicate_reject.json()["error"] == "agent_approval_not_pending"

    # A waiting run whose approval was invalidated fails closed on restart.
    orphan_fake = FakeChatGenerator(
        [
            tool_call_result(
                "save_memory",
                {"content": "Orphaned approval.", "user_confirmed": True},
                call_id="call_orphan_memory",
            )
        ]
    )
    client.app.state.agent_chat_generator = orphan_fake
    orphan_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Orphaned approval"},
    ).json()
    orphan_waiting = client.post(
        f"/api/v1/agent/conversations/{orphan_conversation['id']}/messages",
        json={"content": "Save the orphan note."},
        headers={"Accept": "application/json"},
    ).json()
    assert orphan_waiting["run"]["status"] == "waiting"
    orphan_approval_id = orphan_waiting["pending_approvals"][0]["id"]
    orphan_run_id = orphan_waiting["run"]["id"]
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE agent_approval SET status = 'expired', resolved_at = now() "
                "WHERE id = :approval_id"
            ),
            {"approval_id": orphan_approval_id},
        )
    engine.dispose()

    with TestClient(create_app(settings)):
        pass

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        orphan_status, orphan_error = connection.execute(
            text("SELECT status, error_code FROM agent_run WHERE id = :run_id"),
            {"run_id": orphan_run_id},
        ).one()
    engine.dispose()
    assert orphan_status == "failed"
    assert orphan_error == "approval_orphaned"
    orphan_resolution = client.post(
        f"/api/v1/agent/approvals/{orphan_approval_id}/approve",
        headers={"Accept": "application/json"},
    )
    assert orphan_resolution.status_code == 409
    assert orphan_resolution.json()["error"] == "agent_approval_not_pending"

    # Archiving a conversation expires the pending write and fails closed.
    archive_fake = FakeChatGenerator(
        [
            tool_call_result(
                "save_memory",
                {"content": "Archived approval.", "user_confirmed": True},
                call_id="call_archived_memory",
            )
        ]
    )
    client.app.state.agent_chat_generator = archive_fake
    archive_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Archived approval"},
    ).json()
    archive_waiting = client.post(
        f"/api/v1/agent/conversations/{archive_conversation['id']}/messages",
        json={"content": "Save the archived note."},
        headers={"Accept": "application/json"},
    ).json()
    assert archive_waiting["run"]["status"] == "waiting"
    archive_approval_id = archive_waiting["pending_approvals"][0]["id"]
    archived_approval_conversation = client.patch(
        f"/api/v1/agent/conversations/{archive_conversation['id']}",
        json={"status": "archived"},
    )
    assert archived_approval_conversation.status_code == 200
    archived_resolution = client.post(
        f"/api/v1/agent/approvals/{archive_approval_id}/approve",
        headers={"Accept": "application/json"},
    )
    assert archived_resolution.status_code == 409
    assert archived_resolution.json()["error"] == "agent_conversation_archived"
    assert memory_count() == approved_memories

    # ------------------------------------------------------------------
    # save_memory_requires_approval=false: the backend authorizes the write
    # immediately. No waiting run or approval row is created, and the model's
    # own user_confirmed=false does not prevent it because authorization is
    # backend-side.
    # ------------------------------------------------------------------
    current_settings = client.get("/api/v1/agent/settings").json()["config"]
    disabled_settings = {
        **current_settings,
        "save_memory_requires_approval": False,
    }
    disabled_response = client.put(
        "/api/v1/agent/settings",
        json=disabled_settings,
    )
    assert disabled_response.status_code == 200, disabled_response.text
    assert disabled_response.json()["config"]["save_memory_requires_approval"] is False

    direct_content = "Direct memory with the approval gate disabled."
    direct_fake = FakeChatGenerator(
        [
            tool_call_result(
                "save_memory",
                {"content": direct_content, "user_confirmed": False},
                call_id="call_direct_memory",
            ),
            text_result("Saved directly with backend authorization."),
        ]
    )
    client.app.state.agent_chat_generator = direct_fake
    direct_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Direct memory write"},
    ).json()
    before_direct_memories = memory_count()
    direct_turn = client.post(
        f"/api/v1/agent/conversations/{direct_conversation['id']}/messages",
        json={"content": "Save this memory directly."},
        headers={"Accept": "application/json"},
    )
    assert direct_turn.status_code == 200, direct_turn.text
    direct_body = direct_turn.json()
    assert direct_body["run"]["status"] == "completed"
    assert direct_body["pending_approvals"] == []
    assert direct_body["answer"] == "Saved directly with backend authorization."
    assert [entry["kind"] for entry in direct_body["entries"]] == [
        "pi.user",
        "pi.assistant",
        "pi.tool-result",
        "pi.assistant",
    ]
    direct_results = [
        entry for entry in direct_body["tool_results"] if entry["data"]["tool"] == "save_memory"
    ]
    assert len(direct_results) == 1
    assert direct_results[0]["data"]["status"] == "ok"
    assert direct_results[0]["data"]["memory_id"] > 0
    assert direct_results[0]["model"][0]["tool_call_id"] == "call_direct_memory"
    assert memory_count() == before_direct_memories + 1
    direct_approvals = client.get(
        f"/api/v1/agent/conversations/{direct_conversation['id']}/approvals"
    )
    assert direct_approvals.status_code == 200, direct_approvals.text
    assert direct_approvals.json()["resources"] == []

    # Turning the setting off never resolves an already-pending approval. The
    # row stays explicit, its card data remains available, and no write occurs
    # until a human approves it.
    restored_settings = client.put(
        "/api/v1/agent/settings",
        json=current_settings,
    )
    assert restored_settings.status_code == 200, restored_settings.text
    assert restored_settings.json()["config"]["save_memory_requires_approval"] is True

    pending_fake = FakeChatGenerator(
        [
            tool_call_result(
                "save_memory",
                {
                    "content": "Pending memory across a toggle change.",
                    "user_confirmed": True,
                },
                call_id="call_pending_toggle",
            ),
            text_result("The pending memory was approved."),
        ]
    )
    client.app.state.agent_chat_generator = pending_fake
    pending_conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Pending across toggle"},
    ).json()
    pending_waiting = client.post(
        f"/api/v1/agent/conversations/{pending_conversation['id']}/messages",
        json={"content": "Save the pending memory."},
        headers={"Accept": "application/json"},
    )
    assert pending_waiting.status_code == 200, pending_waiting.text
    pending_body = pending_waiting.json()
    assert pending_body["run"]["status"] == "waiting"
    pending_approval_id = pending_body["pending_approvals"][0]["id"]
    before_pending_memories = memory_count()

    disable_again = client.put(
        "/api/v1/agent/settings",
        json=disabled_settings,
    )
    assert disable_again.status_code == 200, disable_again.text
    still_pending = client.get(
        f"/api/v1/agent/conversations/{pending_conversation['id']}/approvals"
    )
    assert still_pending.status_code == 200, still_pending.text
    still_pending_body = still_pending.json()
    assert [item["id"] for item in still_pending_body["resources"]] == [pending_approval_id]
    assert still_pending_body["resources"][0]["status"] == "pending"
    assert memory_count() == before_pending_memories

    enable_again = client.put(
        "/api/v1/agent/settings",
        json=current_settings,
    )
    assert enable_again.status_code == 200, enable_again.text
    pending_approved = client.post(
        f"/api/v1/agent/approvals/{pending_approval_id}/approve",
        headers={"Accept": "application/json"},
    )
    assert pending_approved.status_code == 200, pending_approved.text
    assert pending_approved.json()["run"]["status"] == "completed"
    assert memory_count() == before_pending_memories + 1

    # Leave the singleton setting at its documented default.
    final_settings_reset = client.post("/api/v1/agent/settings/reset")
    assert final_settings_reset.status_code == 200, final_settings_reset.text
    final_settings_body = final_settings_reset.json()
    assert final_settings_body["config"] == defaults
    assert final_settings_body["config"]["save_memory_requires_approval"] is True
