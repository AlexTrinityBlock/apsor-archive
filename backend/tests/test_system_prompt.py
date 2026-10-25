"""Custom system prompt plus the DB-backed frequently used prompt list."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.module.agent.test.fake_chat_generator import FakeChatGenerator
from tests.conftest import TEST_DATABASE_URL


def test_system_prompt_module_and_section_order(client: TestClient) -> None:
    """Prompt edits affect new conversations only and stay ahead of built-ins."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])

    url = "/api/v1/agent/settings/system-prompt"
    initial = client.get(url)
    assert initial.status_code == 200, initial.text
    assert initial.json()["is_custom"] is False
    assert initial.json()["title"] == ""
    assert initial.json()["body"] == ""

    blank = client.put(url, json={"title": "   ", "body": "Prefer short answers."})
    assert blank.status_code == 422, blank.text
    assert blank.json()["error"] == "agent_invalid_system_prompt"

    updated = client.put(
        url,
        json={
            "title": "Archive voice",
            "body": "Prefer short answers and name the cited file.",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_custom"] is True
    assert updated.json()["title"] == "Archive voice"

    created = client.post("/api/v1/agent/conversations", json={"title": "Prompt order"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    detail = client.get(f"/api/v1/agent/conversations/{conversation_id}")
    assert detail.status_code == 200, detail.text
    system = next(entry for entry in detail.json()["entries"] if entry["kind"] == "pi.system")
    sections = system["data"]["sections"]
    assert [section["name"] for section in sections] == [
        "system_prompt",
        "identity",
        "instructions",
        "examples",
        "context_protocol",
    ]
    assert sections[0] == {
        "name": "system_prompt",
        "title": "Archive voice",
        "content": "Prefer short answers and name the cited file.",
    }
    prompt = system["model"][0]["content"]
    assert prompt.index("# Archive voice") < prompt.index("# Identity")

    changed = client.put(
        url,
        json={
            "title": "Second voice",
            "body": "Answer in the keeper's language.",
        },
    )
    assert changed.status_code == 200, changed.text

    old_detail = client.get(f"/api/v1/agent/conversations/{conversation_id}").json()
    old_system = next(entry for entry in old_detail["entries"] if entry["kind"] == "pi.system")
    assert old_system["data"]["sections"][0]["title"] == "Archive voice"

    second = client.post("/api/v1/agent/conversations", json={"title": "New prompt"})
    assert second.status_code == 201, second.text
    second_detail = client.get(f"/api/v1/agent/conversations/{second.json()['id']}").json()
    second_system = next(
        entry for entry in second_detail["entries"] if entry["kind"] == "pi.system"
    )
    assert second_system["data"]["sections"][0]["title"] == "Second voice"

    reset = client.post(f"{url}/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["is_custom"] is False

    third = client.post("/api/v1/agent/conversations", json={"title": "Built-in only"})
    assert third.status_code == 201, third.text
    third_detail = client.get(f"/api/v1/agent/conversations/{third.json()['id']}").json()
    third_system = next(entry for entry in third_detail["entries"] if entry["kind"] == "pi.system")
    third_names = [section["name"] for section in third_system["data"]["sections"]]
    assert "system_prompt" not in third_names
    assert third_names[0] == "identity"

    # ------------------------------------------------------------------
    # Frequently used prompts: CRUD, whitespace validation, ordering, the
    # 20-row cap, identity monotonicity, and scoped cache invalidation.
    # ------------------------------------------------------------------
    prompts_url = "/api/v1/settings/frequent-prompts"
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

    first_created = client.post(
        prompts_url,
        json={
            "title": "  Alpha prompt  ",
            "prompt_text": "  Summarise the archive.  ",
            "sort_order": 30,
        },
    )
    assert first_created.status_code == 201, first_created.text
    first_prompt = first_created.json()
    first_prompt_id = first_prompt["id"]
    assert first_prompt["title"] == "Alpha prompt"
    assert first_prompt["prompt_text"] == "Summarise the archive."
    assert first_prompt["sort_order"] == 30

    listed = client.get(prompts_url)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["resources"]] == [first_prompt_id]

    edited = client.put(
        f"{prompts_url}/{first_prompt_id}",
        json={
            "title": "Alpha edited",
            "prompt_text": "Trace the newest memory.",
            "sort_order": 10,
        },
    )
    assert edited.status_code == 200, edited.text
    edited_prompt = edited.json()
    assert edited_prompt["id"] == first_prompt_id
    assert edited_prompt["title"] == "Alpha edited"
    assert edited_prompt["prompt_text"] == "Trace the newest memory."
    assert edited_prompt["sort_order"] == 10
    assert edited_prompt["updated_at"] >= edited_prompt["created_at"]

    after_edit = client.get(prompts_url).json()["resources"]
    assert [item["title"] for item in after_edit] == ["Alpha edited"]

    removed = client.delete(f"{prompts_url}/{first_prompt_id}")
    assert removed.status_code == 204
    assert client.get(prompts_url).json()["resources"] == []

    second_created = client.post(
        prompts_url,
        json={
            "title": "Beta prompt",
            "prompt_text": "Open a file from the library.",
            "sort_order": 20,
        },
    )
    assert second_created.status_code == 201, second_created.text
    second_prompt_id = second_created.json()["id"]
    assert second_prompt_id > first_prompt_id

    # Prime the list cache, then edit the row directly in PostgreSQL. The next
    # GET must still return the cached snapshot; a real write bumps the
    # "prompts" scope and the following GET sees the database edit.
    cached = client.get(prompts_url)
    assert cached.status_code == 200
    cache = client.app.state.cache
    assert client.portal is not None
    prompts_version_before = client.portal.call(cache.get_version, "prompts")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE frequently_used_prompt SET title = :title WHERE id = :prompt_id"),
            {"title": "Direct database title", "prompt_id": second_prompt_id},
        )
    engine.dispose()

    stale = client.get(prompts_url)
    assert stale.status_code == 200
    assert [item["title"] for item in stale.json()["resources"]] == ["Beta prompt"]

    third_created = client.post(
        prompts_url,
        json={
            "title": "Ordering prompt",
            "prompt_text": "Check sort order.",
            "sort_order": 5,
        },
    )
    assert third_created.status_code == 201, third_created.text
    third_prompt_id = third_created.json()["id"]
    prompts_version_after = client.portal.call(cache.get_version, "prompts")
    assert prompts_version_after == prompts_version_before + 1

    refreshed = client.get(prompts_url)
    assert refreshed.status_code == 200
    refreshed_resources = refreshed.json()["resources"]
    assert [item["title"] for item in refreshed_resources] == [
        "Ordering prompt",
        "Direct database title",
    ]
    assert refreshed.json()["total_results"] == 2

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
