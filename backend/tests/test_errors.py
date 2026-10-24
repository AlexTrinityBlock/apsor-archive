"""Error envelopes, validation, and fail-closed AI configuration."""

from fastapi.testclient import TestClient


def test_validation_and_error_envelope(client: TestClient) -> None:
    empty_query = client.get("/api/v1/search", params={"query": ""})
    assert empty_query.status_code == 400
    assert empty_query.json()["error"] == "invalid_request"

    traversal = client.post(
        "/api/v1/files/text",
        json={"path": "/../etc/passwd", "content": "blocked"},
    )
    assert traversal.status_code == 422
    assert traversal.json()["error"] == "invalid_path"

    missing = client.get("/api/v1/files/999999")
    assert missing.status_code == 404
    assert missing.json()["error"] == "file_not_found"

    invalid_date = client.get(
        "/api/v1/timeline",
        params={"year": 2026, "month": 2, "day": 30, "day_range": 1},
    )
    assert invalid_date.status_code == 422
    assert invalid_date.json()["error"] == "invalid_timeline_range"

    missing_ai = client.get("/api/v1/ai/status")
    assert missing_ai.status_code == 200
    assert missing_ai.json()["configured"] is False

    conversation = client.post("/api/v1/agent/conversations", json={})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]
    missing_agent = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "What is in the library?"},
        headers={"Accept": "application/json"},
    )
    assert missing_agent.status_code == 503
    assert missing_agent.json()["error"] == "agent_not_configured"
