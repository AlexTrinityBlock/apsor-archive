"""Unified system prompt sections plus the DB-backed frequently used prompts."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.module.agent.service.system_prompt import default_sections
from app.module.agent.test.fake_chat_generator import FakeChatGenerator
from tests.conftest import TEST_DATABASE_URL, UserClient

SYSTEM_PROMPT_URL = "/api/v1/agent/settings/system-prompt"
FREQUENT_PROMPTS_URL = "/api/v1/settings/frequent-prompts"
DEFAULT_TITLES = ["Identity", "Instructions", "Examples", "Context protocol"]


@contextmanager
def _direct_engine() -> Iterator[Engine]:
    """Own a maintenance engine so a failed assertion cannot leak a connection."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


def _list_sections(client: TestClient) -> dict[str, Any]:
    """Return the section collection envelope from the API."""
    response = client.get(SYSTEM_PROMPT_URL)
    assert response.status_code == 200, response.text
    return response.json()


def _create_section(
    client: TestClient,
    *,
    title: str,
    body: str,
    sort_order: int | None = None,
) -> dict[str, Any]:
    """Create one section and return the resulting collection envelope."""
    payload: dict[str, Any] = {"title": title, "body": body}
    if sort_order is not None:
        payload["sort_order"] = sort_order
    response = client.post(SYSTEM_PROMPT_URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _find_section(list_body: dict[str, Any], title: str) -> dict[str, Any]:
    """Find one section by its unique title in a collection envelope."""
    return next(item for item in list_body["resources"] if item["title"] == title)


def _create_conversation(client: TestClient, title: str) -> int:
    """Create a conversation and return its id."""
    response = client.post("/api/v1/agent/conversations", json={"title": title})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _system_entry(client: TestClient, conversation_id: int) -> dict[str, Any]:
    """Return the immutable ``pi.system`` entry of one conversation."""
    response = client.get(f"/api/v1/agent/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    entries = [entry for entry in response.json()["entries"] if entry["kind"] == "pi.system"]
    assert len(entries) == 1
    return entries[0]


def _section_names(system_entry: dict[str, Any]) -> list[str]:
    """Return the provider-visible section names in order."""
    return [section["name"] for section in system_entry["data"]["sections"]]


def _prompt(system_entry: dict[str, Any]) -> str:
    """Return the rendered provider system message."""
    return system_entry["model"][0]["content"]


def test_system_prompt_module_and_section_order(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """Defaults are ordinary rows: editable, deletable, reorderable, and frozen."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])

    # ------------------------------------------------------------------
    # 1. A fresh database contains the four seeded defaults. They are the same
    # kind of row as every owner-authored section, and their bodies are the
    # seed bodies, not a read-time Python fallback.
    # ------------------------------------------------------------------
    initial = _list_sections(client)
    assert initial["total_results"] == 4
    assert initial["start_index"] == 1
    assert initial["items_per_page"] == 4
    assert [item["title"] for item in initial["resources"]] == DEFAULT_TITLES
    assert [item["sort_order"] for item in initial["resources"]] == [10, 20, 30, 40]
    assert [item["body"] for item in initial["resources"]] == [
        section["body"] for section in default_sections()
    ]
    default_ids = [item["id"] for item in initial["resources"]]

    # ------------------------------------------------------------------
    # 2. Create two sections: one appends at max + 10, one is inserted before
    # the defaults. The list follows sort_order and then id.
    # ------------------------------------------------------------------
    late_created = _create_section(client, title="Late", body="Late body.")
    late_id = _find_section(late_created, "Late")["id"]
    assert _find_section(late_created, "Late")["sort_order"] == 50

    early_created = _create_section(
        client,
        title="Early",
        body="Early body.",
        sort_order=5,
    )
    early_id = _find_section(early_created, "Early")["id"]
    assert _find_section(early_created, "Early")["sort_order"] == 5

    listed = _list_sections(client)
    assert listed["total_results"] == 6
    assert [item["title"] for item in listed["resources"]] == [
        "Early",
        *DEFAULT_TITLES,
        "Late",
    ]
    assert [item["sort_order"] for item in listed["resources"]] == [5, 10, 20, 30, 40, 50]

    # ------------------------------------------------------------------
    # 3. Reorder the complete collection. A missing, unknown, or duplicate id
    # must be rejected without changing the stored order.
    # ------------------------------------------------------------------
    reordered_ids = [late_id, *reversed(default_ids), early_id]
    reordered = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": reordered_ids},
    )
    assert reordered.status_code == 200, reordered.text
    assert [item["id"] for item in reordered.json()["resources"]] == reordered_ids
    assert [item["sort_order"] for item in reordered.json()["resources"]] == [
        10,
        20,
        30,
        40,
        50,
        60,
    ]
    assert [item["id"] for item in _list_sections(client)["resources"]] == reordered_ids

    missing_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [late_id]},
    )
    assert missing_id.status_code == 422, missing_id.text
    assert missing_id.json()["error"] == "agent_invalid_system_prompt"

    unknown_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [*reordered_ids, 999_999]},
    )
    assert unknown_id.status_code == 422, unknown_id.text
    assert unknown_id.json()["error"] == "agent_invalid_system_prompt"

    duplicate_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [late_id, late_id, *default_ids, early_id]},
    )
    assert duplicate_id.status_code == 422, duplicate_id.text
    assert duplicate_id.json()["error"] == "agent_invalid_system_prompt"
    assert [item["id"] for item in _list_sections(client)["resources"]] == reordered_ids

    # ------------------------------------------------------------------
    # 4. A new conversation freezes every row in the current order. The
    # provider sees ``system_prompt:<id>`` for all rows, including defaults.
    # ------------------------------------------------------------------
    conversation_id = _create_conversation(client, "Ordered sections")
    system_entry = _system_entry(client, conversation_id)
    assert _section_names(system_entry) == [
        f"system_prompt:{section_id}" for section_id in reordered_ids
    ]
    assert system_entry["data"]["prompt_version"] == "archive-agent-v12"
    sections = system_entry["data"]["sections"]
    assert sections[0] == {
        "name": f"system_prompt:{late_id}",
        "title": "Late",
        "content": "Late body.",
    }
    assert sections[5] == {
        "name": f"system_prompt:{early_id}",
        "title": "Early",
        "content": "Early body.",
    }
    prompt = _prompt(system_entry)
    assert "# Late" in prompt
    assert "# Early" in prompt
    assert prompt.index("# Late") < prompt.index("# Context protocol") < prompt.index("# Early")

    # ------------------------------------------------------------------
    # 5. Editing any row, including a default, only affects conversations
    # created afterwards. The old ``pi.system`` entry stays byte-identical.
    # ------------------------------------------------------------------
    identity_id = default_ids[0]
    edited_default = client.put(
        f"{SYSTEM_PROMPT_URL}/{identity_id}",
        json={"title": "Who I am", "body": "Edited identity body."},
    )
    assert edited_default.status_code == 200, edited_default.text
    edited_identity = _find_section(edited_default.json(), "Who I am")
    assert edited_identity["id"] == identity_id
    assert edited_identity["sort_order"] == 50

    edited_custom = client.put(
        f"{SYSTEM_PROMPT_URL}/{early_id}",
        json={"title": "Early edited", "body": "Early body edited."},
    )
    assert edited_custom.status_code == 200, edited_custom.text

    frozen = _system_entry(client, conversation_id)
    assert frozen["model"] == system_entry["model"]
    assert frozen["data"] == system_entry["data"]
    assert "# Who I am" not in _prompt(frozen)
    assert "# Early edited" not in _prompt(frozen)

    edited_conversation_id = _create_conversation(client, "Edited sections")
    edited_entry = _system_entry(client, edited_conversation_id)
    assert _section_names(edited_entry) == [
        f"system_prompt:{section_id}" for section_id in reordered_ids
    ]
    assert edited_entry["data"]["sections"][4]["title"] == "Who I am"
    assert edited_entry["data"]["sections"][4]["content"] == "Edited identity body."
    assert edited_entry["data"]["sections"][-1]["title"] == "Early edited"
    edited_prompt = _prompt(edited_entry)
    assert "# Who I am" in edited_prompt
    assert "# Early edited" in edited_prompt

    # ------------------------------------------------------------------
    # 6. Deleting a default and a custom row removes both from new
    # conversations. Older conversations keep their frozen copy.
    # ------------------------------------------------------------------
    examples_id = default_ids[2]
    assert client.delete(f"{SYSTEM_PROMPT_URL}/{examples_id}").status_code == 204
    assert client.delete(f"{SYSTEM_PROMPT_URL}/{late_id}").status_code == 204
    remaining = _list_sections(client)
    assert remaining["total_results"] == 4
    assert [item["id"] for item in remaining["resources"]] == [
        default_ids[3],
        default_ids[1],
        identity_id,
        early_id,
    ]

    after_delete_id = _create_conversation(client, "After delete")
    after_delete_entry = _system_entry(client, after_delete_id)
    assert _section_names(after_delete_entry) == [
        f"system_prompt:{section_id}"
        for section_id in [default_ids[3], default_ids[1], identity_id, early_id]
    ]
    after_delete_prompt = _prompt(after_delete_entry)
    assert "# Examples" not in after_delete_prompt
    assert "# Late" not in after_delete_prompt
    assert "# Who I am" in after_delete_prompt
    assert _section_names(_system_entry(client, edited_conversation_id)) == [
        f"system_prompt:{section_id}" for section_id in reordered_ids
    ]

    # ------------------------------------------------------------------
    # 7. Reset removes custom rows and restores the four defaults as fresh
    # rows. New conversations see only the defaults in canonical order.
    # ------------------------------------------------------------------
    previous_max = max(item["id"] for item in remaining["resources"])
    reset = client.post(f"{SYSTEM_PROMPT_URL}/reset")
    assert reset.status_code == 200, reset.text
    reset_body = reset.json()
    assert reset_body["total_results"] == 4
    assert [item["title"] for item in reset_body["resources"]] == DEFAULT_TITLES
    assert [item["sort_order"] for item in reset_body["resources"]] == [10, 20, 30, 40]
    assert all(item["id"] > previous_max for item in reset_body["resources"])
    assert _list_sections(client)["total_results"] == 4

    reset_conversation_id = _create_conversation(client, "After reset")
    reset_entry = _system_entry(client, reset_conversation_id)
    assert _section_names(reset_entry) == [
        f"system_prompt:{item['id']}" for item in reset_body["resources"]
    ]
    reset_prompt = _prompt(reset_entry)
    assert "# Identity" in reset_prompt
    assert "# Who I am" not in reset_prompt
    assert "# Early edited" not in reset_prompt

    # ------------------------------------------------------------------
    # 8. Whitespace-only titles and bodies are rejected on create and update
    # with the stable agent_invalid_system_prompt error.
    # ------------------------------------------------------------------
    blank_title = client.post(SYSTEM_PROMPT_URL, json={"title": "   ", "body": "A body."})
    assert blank_title.status_code == 422, blank_title.text
    assert blank_title.json()["error"] == "agent_invalid_system_prompt"

    blank_body = client.post(SYSTEM_PROMPT_URL, json={"title": "A title", "body": "\n\t "})
    assert blank_body.status_code == 422, blank_body.text
    assert blank_body.json()["error"] == "agent_invalid_system_prompt"
    assert _list_sections(client)["total_results"] == 4

    editable_created = _create_section(client, title="Editable", body="Original body.")
    editable_id = _find_section(editable_created, "Editable")["id"]

    blank_update_title = client.put(
        f"{SYSTEM_PROMPT_URL}/{editable_id}",
        json={"title": "   ", "body": "Original body."},
    )
    assert blank_update_title.status_code == 422, blank_update_title.text
    assert blank_update_title.json()["error"] == "agent_invalid_system_prompt"

    blank_update_body = client.put(
        f"{SYSTEM_PROMPT_URL}/{editable_id}",
        json={"title": "Editable", "body": "   "},
    )
    assert blank_update_body.status_code == 422, blank_update_body.text
    assert blank_update_body.json()["error"] == "agent_invalid_system_prompt"

    unchanged = next(
        item for item in _list_sections(client)["resources"] if item["id"] == editable_id
    )
    assert unchanged["title"] == "Editable"
    assert unchanged["body"] == "Original body."

    # ------------------------------------------------------------------
    # 9. Deleting a section does not rewind the identity sequence.
    # ------------------------------------------------------------------
    assert client.delete(f"{SYSTEM_PROMPT_URL}/{editable_id}").status_code == 204
    fresh_created = _create_section(client, title="Fresh", body="Fresh body.")
    fresh_id = _find_section(fresh_created, "Fresh")["id"]
    assert fresh_id > editable_id
    assert fresh_id > max(item["id"] for item in reset_body["resources"])

    # ------------------------------------------------------------------
    # 10. The list is cached under the system_prompts scope. A direct database
    # edit stays hidden until a real write bumps that scope, which leaves the
    # archive index scope untouched.
    # ------------------------------------------------------------------
    assert client.post(f"{SYSTEM_PROMPT_URL}/reset").status_code == 200
    cached_created = _create_section(client, title="Cached title", body="Cached body.")
    cached_id = _find_section(cached_created, "Cached title")["id"]

    cache = client.app.state.cache
    assert client.portal is not None
    version_before = client.portal.call(cache.get_version, "system_prompts")
    index_before = client.portal.call(
        cache.get_version,
        f"u:{root_account.user_id}:index",
    )

    primed = _list_sections(client)
    assert [item["title"] for item in primed["resources"]] == [
        *DEFAULT_TITLES,
        "Cached title",
    ]

    with _direct_engine() as engine, engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE system_prompt_section SET title = :title, body = :body "
                "WHERE id = :section_id"
            ),
            {
                "title": "Direct database title",
                "body": "Direct database body.",
                "section_id": cached_id,
            },
        )
        direct_title = connection.execute(
            text("SELECT title FROM system_prompt_section WHERE id = :section_id"),
            {"section_id": cached_id},
        ).scalar_one()
    assert direct_title == "Direct database title"

    stale = _list_sections(client)
    assert [item["title"] for item in stale["resources"]] == [
        *DEFAULT_TITLES,
        "Cached title",
    ]

    second_created = _create_section(client, title="Cache buster", body="Second body.")
    second_id = _find_section(second_created, "Cache buster")["id"]
    assert second_id > cached_id

    version_after = client.portal.call(cache.get_version, "system_prompts")
    index_after = client.portal.call(
        cache.get_version,
        f"u:{root_account.user_id}:index",
    )
    assert version_after == version_before + 1
    assert index_after == index_before

    refreshed = _list_sections(client)
    assert refreshed["total_results"] == 6
    assert [item["title"] for item in refreshed["resources"]] == [
        *DEFAULT_TITLES,
        "Direct database title",
        "Cache buster",
    ]
    assert refreshed["resources"][4]["body"] == "Direct database body."

    # ------------------------------------------------------------------
    # Frequently used prompts: CRUD, whitespace validation, ordering, the
    # 20-row cap, identity monotonicity, and scoped cache invalidation.
    # ------------------------------------------------------------------
    prompts_url = FREQUENT_PROMPTS_URL
    empty_list = client.get(prompts_url)
    assert empty_list.status_code == 200, empty_list.text
    assert empty_list.json()["resources"] == []
    assert empty_list.json()["total_results"] == 0

    whitespace_title = client.post(
        prompts_url,
        json={"title": "   ", "prompt_text": "Useful prompt body."},
    )
    assert whitespace_title.status_code == 422, whitespace_title.text
    assert whitespace_title.json()["error"] == "invalid_frequent_prompt"
    whitespace_text = client.post(
        prompts_url,
        json={"title": "Useful title", "prompt_text": "   "},
    )
    assert whitespace_text.status_code == 422, whitespace_text.text
    assert whitespace_text.json()["error"] == "invalid_frequent_prompt"

    first_prompt_created = client.post(
        prompts_url,
        json={
            "title": "  Alpha prompt  ",
            "prompt_text": "  Summarise the archive.  ",
            "sort_order": 30,
        },
    )
    assert first_prompt_created.status_code == 201, first_prompt_created.text
    first_prompt = first_prompt_created.json()
    first_prompt_id = first_prompt["id"]
    assert first_prompt["title"] == "Alpha prompt"
    assert first_prompt["prompt_text"] == "Summarise the archive."
    assert first_prompt["sort_order"] == 30

    prompts_listed = client.get(prompts_url)
    assert prompts_listed.status_code == 200
    assert [item["id"] for item in prompts_listed.json()["resources"]] == [first_prompt_id]

    prompt_edited = client.put(
        f"{prompts_url}/{first_prompt_id}",
        json={
            "title": "Alpha edited",
            "prompt_text": "Trace the newest memory.",
            "sort_order": 10,
        },
    )
    assert prompt_edited.status_code == 200, prompt_edited.text
    edited_prompt = prompt_edited.json()
    assert edited_prompt["id"] == first_prompt_id
    assert edited_prompt["title"] == "Alpha edited"
    assert edited_prompt["prompt_text"] == "Trace the newest memory."
    assert edited_prompt["sort_order"] == 10
    assert edited_prompt["updated_at"] >= edited_prompt["created_at"]

    after_prompt_edit = client.get(prompts_url).json()["resources"]
    assert [item["title"] for item in after_prompt_edit] == ["Alpha edited"]

    prompt_removed = client.delete(f"{prompts_url}/{first_prompt_id}")
    assert prompt_removed.status_code == 204
    assert client.get(prompts_url).json()["resources"] == []

    second_prompt_created = client.post(
        prompts_url,
        json={
            "title": "Beta prompt",
            "prompt_text": "Open a file from the library.",
            "sort_order": 20,
        },
    )
    assert second_prompt_created.status_code == 201, second_prompt_created.text
    second_prompt_id = second_prompt_created.json()["id"]
    assert second_prompt_id > first_prompt_id

    # Prime the list cache, then edit the row directly in PostgreSQL. The next
    # GET must still return the cached snapshot; a real write bumps the acting
    # user's "u:{user_id}:prompts" scope and the following GET sees the edit.
    prompts_cached = client.get(prompts_url)
    assert prompts_cached.status_code == 200
    prompts_scope = f"u:{root_account.user_id}:prompts"
    prompts_version_before = client.portal.call(cache.get_version, prompts_scope)

    with _direct_engine() as prompts_engine, prompts_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE frequently_used_prompt SET title = :title "
                "WHERE id = :prompt_id AND user_id = :user_id"
            ),
            {
                "title": "Direct database title",
                "prompt_id": second_prompt_id,
                "user_id": root_account.user_id,
            },
        )

    prompts_stale = client.get(prompts_url)
    assert prompts_stale.status_code == 200
    assert [item["title"] for item in prompts_stale.json()["resources"]] == ["Beta prompt"]

    third_prompt_created = client.post(
        prompts_url,
        json={
            "title": "Ordering prompt",
            "prompt_text": "Check sort order.",
            "sort_order": 5,
        },
    )
    assert third_prompt_created.status_code == 201, third_prompt_created.text
    third_prompt_id = third_prompt_created.json()["id"]
    prompts_version_after = client.portal.call(cache.get_version, prompts_scope)
    assert prompts_version_after == prompts_version_before + 1

    prompts_refreshed = client.get(prompts_url)
    assert prompts_refreshed.status_code == 200
    refreshed_resources = prompts_refreshed.json()["resources"]
    assert [item["title"] for item in refreshed_resources] == [
        "Ordering prompt",
        "Direct database title",
    ]
    assert prompts_refreshed.json()["total_results"] == 2

    assert client.delete(f"{prompts_url}/{third_prompt_id}").status_code == 204
    ordering_after_delete = client.get(prompts_url).json()["resources"]
    assert [item["title"] for item in ordering_after_delete] == ["Direct database title"]

    # ------------------------------------------------------------------
    # Drag reorder: one request carries the complete order, and the server
    # rewrites sort_order as 10/20/30. Add two rows so three prompts exist.
    # ------------------------------------------------------------------
    gamma_prompt_created = client.post(
        prompts_url,
        json={
            "title": "Gamma prompt",
            "prompt_text": "Compare three sources.",
            "sort_order": 30,
        },
    )
    assert gamma_prompt_created.status_code == 201, gamma_prompt_created.text
    gamma_prompt_id = gamma_prompt_created.json()["id"]

    delta_prompt_created = client.post(
        prompts_url,
        json={
            "title": "Delta prompt",
            "prompt_text": "Draft a weekly summary.",
            "sort_order": 40,
        },
    )
    assert delta_prompt_created.status_code == 201, delta_prompt_created.text
    delta_prompt_id = delta_prompt_created.json()["id"]

    initial_prompt_ids = [second_prompt_id, gamma_prompt_id, delta_prompt_id]
    reordered_prompt_ids = list(reversed(initial_prompt_ids))
    reorder_response = client.post(
        f"{prompts_url}/reorder",
        json={"prompt_ids": reordered_prompt_ids},
    )
    assert reorder_response.status_code == 200, reorder_response.text
    reordered_prompts = reorder_response.json()["resources"]
    assert [item["id"] for item in reordered_prompts] == reordered_prompt_ids
    assert [item["sort_order"] for item in reordered_prompts] == [10, 20, 30]

    persisted_prompts = client.get(prompts_url).json()["resources"]
    assert [item["id"] for item in persisted_prompts] == reordered_prompt_ids
    assert [item["sort_order"] for item in persisted_prompts] == [10, 20, 30]

    # 重送同一份順序必須 idempotent，回傳與資料庫都維持相同結果。
    repeated_reorder = client.post(
        f"{prompts_url}/reorder",
        json={"prompt_ids": reordered_prompt_ids},
    )
    assert repeated_reorder.status_code == 200, repeated_reorder.text
    assert [item["id"] for item in repeated_reorder.json()["resources"]] == reordered_prompt_ids
    assert [item["sort_order"] for item in repeated_reorder.json()["resources"]] == [10, 20, 30]

    # 缺少 id、重複 id、未知 id 都是 422，且不會改動已儲存的順序。
    missing_reorder = client.post(
        f"{prompts_url}/reorder",
        json={"prompt_ids": reordered_prompt_ids[:-1]},
    )
    assert missing_reorder.status_code == 422, missing_reorder.text
    assert missing_reorder.json()["error"] == "invalid_frequent_prompt"

    duplicate_reorder = client.post(
        f"{prompts_url}/reorder",
        json={"prompt_ids": [*reordered_prompt_ids, reordered_prompt_ids[0]]},
    )
    assert duplicate_reorder.status_code == 422, duplicate_reorder.text
    assert duplicate_reorder.json()["error"] == "invalid_frequent_prompt"

    unknown_reorder = client.post(
        f"{prompts_url}/reorder",
        json={"prompt_ids": [*reordered_prompt_ids, 999_999]},
    )
    assert unknown_reorder.status_code == 422, unknown_reorder.text
    assert unknown_reorder.json()["error"] == "invalid_frequent_prompt"

    # 空清單由 Pydantic 的 min_length 擋下，走共用的 invalid_request envelope。
    empty_reorder = client.post(f"{prompts_url}/reorder", json={"prompt_ids": []})
    assert empty_reorder.status_code == 400, empty_reorder.text
    assert empty_reorder.json()["error"] == "invalid_request"

    unchanged_after_rejections = client.get(prompts_url).json()["resources"]
    assert [item["id"] for item in unchanged_after_rejections] == reordered_prompt_ids
    assert [item["sort_order"] for item in unchanged_after_rejections] == [10, 20, 30]

    # 移除額外建立的兩筆，讓後面的 20 筆上限測試仍從單一 prompt 開始。
    assert client.delete(f"{prompts_url}/{gamma_prompt_id}").status_code == 204
    assert client.delete(f"{prompts_url}/{delta_prompt_id}").status_code == 204
    assert [item["id"] for item in client.get(prompts_url).json()["resources"]] == [
        second_prompt_id
    ]

    # Fill to exactly 20 rows, then reject the 21st.
    for index in range(19):
        created_prompt = client.post(
            prompts_url,
            json={
                "title": f"Bulk prompt {index:02d}",
                "prompt_text": f"Bulk prompt text {index:02d}.",
                "sort_order": 100 + index,
            },
        )
        assert created_prompt.status_code == 201, created_prompt.text

    capped_list = client.get(prompts_url)
    assert capped_list.status_code == 200
    assert capped_list.json()["total_results"] == 20
    assert len(capped_list.json()["resources"]) == 20

    rejected = client.post(
        prompts_url,
        json={
            "title": "One prompt too many",
            "prompt_text": "This row must never be stored.",
            "sort_order": 999,
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "too_many_frequent_prompts"
    assert client.get(prompts_url).json()["total_results"] == 20
