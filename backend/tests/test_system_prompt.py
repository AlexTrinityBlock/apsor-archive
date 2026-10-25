"""The custom system prompt is a first section, frozen per conversation."""

from fastapi.testclient import TestClient

from app.module.agent.test.fake_chat_generator import FakeChatGenerator


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
