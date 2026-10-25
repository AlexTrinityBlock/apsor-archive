"""Ordered system prompt sections plus the DB-backed frequently used prompts."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.module.agent.test.fake_chat_generator import FakeChatGenerator
from tests.conftest import TEST_DATABASE_URL

SYSTEM_PROMPT_URL = "/api/v1/agent/settings/system-prompt"
FREQUENT_PROMPTS_URL = "/api/v1/settings/frequent-prompts"
BUILTIN_SECTION_NAMES = ["identity", "instructions", "examples", "context_protocol"]


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


def test_system_prompt_module_and_section_order(client: TestClient) -> None:
    """Sections are CRUD-managed, ordered, frozen, and cache-invalidated."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])

    # ------------------------------------------------------------------
    # 1. The collection starts empty.
    # ------------------------------------------------------------------
    initial = _list_sections(client)
    assert initial["total_results"] == 0
    assert initial["resources"] == []
    assert initial["start_index"] == 1
    assert initial["items_per_page"] == 0

    # ------------------------------------------------------------------
    # 2. Create two sections; the list follows sort_order and id. The first
    # created row has a higher sort_order, so it must not lead the list.
    # ------------------------------------------------------------------
    first_created = _create_section(client, title="Title 1", body="Body one.", sort_order=20)
    first_section = _find_section(first_created, "Title 1")
    first_id = first_section["id"]
    assert first_section["sort_order"] == 20

    second_created = _create_section(client, title="Title 2", body="Body two.", sort_order=10)
    second_section = _find_section(second_created, "Title 2")
    second_id = second_section["id"]
    assert second_section["sort_order"] == 10
    assert second_id > first_id

    listed = _list_sections(client)
    assert listed["total_results"] == 2
    assert [item["title"] for item in listed["resources"]] == ["Title 2", "Title 1"]
    assert [item["sort_order"] for item in listed["resources"]] == [10, 20]

    # ------------------------------------------------------------------
    # 3. Reorder the complete collection. A missing or unknown id must be
    # rejected without changing the stored order.
    # ------------------------------------------------------------------
    reordered = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [first_id, second_id]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [item["id"] for item in reordered.json()["resources"]] == [first_id, second_id]
    assert [item["sort_order"] for item in reordered.json()["resources"]] == [10, 20]
    assert [item["id"] for item in _list_sections(client)["resources"]] == [first_id, second_id]

    missing_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [first_id]},
    )
    assert missing_id.status_code == 422, missing_id.text
    assert missing_id.json()["error"] == "agent_invalid_system_prompt"

    unknown_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [first_id, second_id, 999_999]},
    )
    assert unknown_id.status_code == 422, unknown_id.text
    assert unknown_id.json()["error"] == "agent_invalid_system_prompt"

    duplicate_id = client.put(
        f"{SYSTEM_PROMPT_URL}/order",
        json={"section_ids": [first_id, first_id]},
    )
    assert duplicate_id.status_code == 422, duplicate_id.text
    assert duplicate_id.json()["error"] == "agent_invalid_system_prompt"

    assert [item["id"] for item in _list_sections(client)["resources"]] == [first_id, second_id]

    # ------------------------------------------------------------------
    # 4. A new conversation freezes both custom sections before the four
    # built-in sections and renders them in order.
    # ------------------------------------------------------------------
    conversation_id = _create_conversation(client, "Ordered sections")
    system_entry = _system_entry(client, conversation_id)
    assert _section_names(system_entry) == [
        f"system_prompt:{first_id}",
        f"system_prompt:{second_id}",
        "identity",
        "instructions",
        "examples",
        "context_protocol",
    ]
    assert system_entry["data"]["prompt_version"] == "archive-agent-v11"
    sections = system_entry["data"]["sections"]
    assert sections[0] == {
        "name": f"system_prompt:{first_id}",
        "title": "Title 1",
        "content": "Body one.",
    }
    assert sections[1] == {
        "name": f"system_prompt:{second_id}",
        "title": "Title 2",
        "content": "Body two.",
    }
    prompt = _prompt(system_entry)
    assert "# Title 1" in prompt
    assert "# Title 2" in prompt
    assert prompt.index("# Title 1") < prompt.index("# Title 2") < prompt.index("# Identity")

    # ------------------------------------------------------------------
    # 5. Editing a section only affects conversations created afterwards.
    # ------------------------------------------------------------------
    edited = client.put(
        f"{SYSTEM_PROMPT_URL}/{first_id}",
        json={"title": "Title 1 edited", "body": "Body one edited."},
    )
    assert edited.status_code == 200, edited.text
    edited_section = _find_section(edited.json(), "Title 1 edited")
    assert edited_section["id"] == first_id
    assert edited_section["sort_order"] == 10

    frozen = _system_entry(client, conversation_id)
    assert frozen["model"] == system_entry["model"]
    assert frozen["data"] == system_entry["data"]
    assert "# Title 1 edited" not in _prompt(frozen)

    edited_conversation_id = _create_conversation(client, "Edited sections")
    edited_entry = _system_entry(client, edited_conversation_id)
    assert _section_names(edited_entry)[:2] == [
        f"system_prompt:{first_id}",
        f"system_prompt:{second_id}",
    ]
    assert edited_entry["data"]["sections"][0]["title"] == "Title 1 edited"
    assert edited_entry["data"]["sections"][0]["content"] == "Body one edited."
    edited_prompt = _prompt(edited_entry)
    assert "# Title 1 edited" in edited_prompt
    assert edited_prompt.index("# Title 1 edited") < edited_prompt.index("# Title 2")

    # ------------------------------------------------------------------
    # 6. Deleting one section leaves the other custom section and the
    # built-ins in new conversations; older conversations stay frozen.
    # ------------------------------------------------------------------
    deleted = client.delete(f"{SYSTEM_PROMPT_URL}/{first_id}")
    assert deleted.status_code == 204, deleted.text
    remaining = _list_sections(client)
    assert remaining["total_results"] == 1
    assert [item["id"] for item in remaining["resources"]] == [second_id]

    after_delete_id = _create_conversation(client, "After delete")
    after_delete_entry = _system_entry(client, after_delete_id)
    assert _section_names(after_delete_entry) == [
        f"system_prompt:{second_id}",
        "identity",
        "instructions",
        "examples",
        "context_protocol",
    ]
    after_delete_prompt = _prompt(after_delete_entry)
    assert "# Title 1 edited" not in after_delete_prompt
    assert "# Title 2" in after_delete_prompt
    assert _section_names(_system_entry(client, edited_conversation_id))[:2] == [
        f"system_prompt:{first_id}",
        f"system_prompt:{second_id}",
    ]

    # ------------------------------------------------------------------
    # 7. Reset clears the collection; new conversations use built-ins only.
    # ------------------------------------------------------------------
    reset = client.post(f"{SYSTEM_PROMPT_URL}/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["total_results"] == 0
    assert reset.json()["resources"] == []
    assert _list_sections(client)["total_results"] == 0

    reset_conversation_id = _create_conversation(client, "After reset")
    reset_entry = _system_entry(client, reset_conversation_id)
    assert _section_names(reset_entry) == BUILTIN_SECTION_NAMES
    reset_prompt = _prompt(reset_entry)
    assert "# Title 1 edited" not in reset_prompt
    assert "# Title 2" not in reset_prompt

    # ------------------------------------------------------------------
    # 8. The four built-in sections are readable and editable. An override is
    # frozen into new conversations; reset restores the Python default.
    # ------------------------------------------------------------------
    builtin_url = f"{SYSTEM_PROMPT_URL}/builtin"
    builtins = client.get(builtin_url)
    assert builtins.status_code == 200, builtins.text
    builtin_body = builtins.json()
    assert [item["key"] for item in builtin_body["resources"]] == BUILTIN_SECTION_NAMES
    assert all(item["customized"] is False for item in builtin_body["resources"])
    default_instructions = next(
        item["body"] for item in builtin_body["resources"] if item["key"] == "instructions"
    )

    custom_instructions = "Edited built-in instructions for this test."
    edited_builtin = client.put(
        f"{builtin_url}/instructions",
        json={"body": custom_instructions},
    )
    assert edited_builtin.status_code == 200, edited_builtin.text
    edited_instructions = next(
        item for item in edited_builtin.json()["resources"] if item["key"] == "instructions"
    )
    assert edited_instructions["customized"] is True
    assert edited_instructions["body"] == custom_instructions

    builtin_conversation_id = _create_conversation(client, "Edited built-in")
    builtin_entry = _system_entry(client, builtin_conversation_id)
    assert _section_names(builtin_entry) == BUILTIN_SECTION_NAMES
    rendered_instructions = next(
        section
        for section in builtin_entry["data"]["sections"]
        if section["name"] == "instructions"
    )
    assert rendered_instructions["content"] == custom_instructions
    assert custom_instructions in _prompt(builtin_entry)

    unknown_builtin = client.put(f"{builtin_url}/not_a_section", json={"body": "Body."})
    assert unknown_builtin.status_code == 404
    blank_builtin = client.put(f"{builtin_url}/instructions", json={"body": "   "})
    assert blank_builtin.status_code == 422
    assert blank_builtin.json()["error"] == "agent_invalid_system_prompt"

    reset_builtin = client.post(f"{builtin_url}/reset")
    assert reset_builtin.status_code == 200, reset_builtin.text
    assert all(item["customized"] is False for item in reset_builtin.json()["resources"])
    reset_instructions = next(
        item["body"] for item in reset_builtin.json()["resources"] if item["key"] == "instructions"
    )
    assert reset_instructions == default_instructions

    restored_conversation_id = _create_conversation(client, "Restored built-in")
    restored_entry = _system_entry(client, restored_conversation_id)
    restored_instructions = next(
        section
        for section in restored_entry["data"]["sections"]
        if section["name"] == "instructions"
    )
    assert restored_instructions["content"] == default_instructions
    assert custom_instructions not in _prompt(restored_entry)

    # ------------------------------------------------------------------
    # 9. Whitespace-only titles and bodies are rejected on create and update
    # with the stable agent_invalid_system_prompt error.
    # ------------------------------------------------------------------
    blank_title = client.post(SYSTEM_PROMPT_URL, json={"title": "   ", "body": "A body."})
    assert blank_title.status_code == 422, blank_title.text
    assert blank_title.json()["error"] == "agent_invalid_system_prompt"

    blank_body = client.post(SYSTEM_PROMPT_URL, json={"title": "A title", "body": "\n\t "})
    assert blank_body.status_code == 422, blank_body.text
    assert blank_body.json()["error"] == "agent_invalid_system_prompt"
    assert _list_sections(client)["total_results"] == 0

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

    unchanged = _list_sections(client)["resources"][0]
    assert unchanged["id"] == editable_id
    assert unchanged["title"] == "Editable"
    assert unchanged["body"] == "Original body."

    # ------------------------------------------------------------------
    # 9. Deleting a section does not rewind the identity sequence.
    # ------------------------------------------------------------------
    assert client.delete(f"{SYSTEM_PROMPT_URL}/{editable_id}").status_code == 204
    fresh_created = _create_section(client, title="Fresh", body="Fresh body.")
    fresh_id = _find_section(fresh_created, "Fresh")["id"]
    assert fresh_id > editable_id
    assert [item["id"] for item in fresh_created["resources"]] == [fresh_id]

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
    index_before = client.portal.call(cache.get_version, "index")

    primed = _list_sections(client)
    assert [item["title"] for item in primed["resources"]] == ["Cached title"]

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
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
    engine.dispose()
    assert direct_title == "Direct database title"

    stale = _list_sections(client)
    assert [item["title"] for item in stale["resources"]] == ["Cached title"]

    second_created = _create_section(client, title="Cache buster", body="Second body.")
    second_id = _find_section(second_created, "Cache buster")["id"]
    assert second_id > cached_id

    version_after = client.portal.call(cache.get_version, "system_prompts")
    index_after = client.portal.call(cache.get_version, "index")
    assert version_after == version_before + 1
    assert index_after == index_before

    refreshed = _list_sections(client)
    assert refreshed["total_results"] == 2
    assert [item["id"] for item in refreshed["resources"]] == [cached_id, second_id]
    assert refreshed["resources"][0]["title"] == "Direct database title"
    assert refreshed["resources"][0]["body"] == "Direct database body."

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
    # GET must still return the cached snapshot; a real write bumps the
    # "prompts" scope and the following GET sees the database edit.
    prompts_cached = client.get(prompts_url)
    assert prompts_cached.status_code == 200
    prompts_version_before = client.portal.call(cache.get_version, "prompts")

    prompts_engine = create_engine(TEST_DATABASE_URL)
    with prompts_engine.begin() as connection:
        connection.execute(
            text("UPDATE frequently_used_prompt SET title = :title WHERE id = :prompt_id"),
            {"title": "Direct database title", "prompt_id": second_prompt_id},
        )
    prompts_engine.dispose()

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
    prompts_version_after = client.portal.call(cache.get_version, "prompts")
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
