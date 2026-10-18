"""Small API helpers shared by integration tests."""

from fastapi.testclient import TestClient


def create_text(
    client: TestClient,
    path: str,
    content: str,
    occurred_at: str | None = None,
) -> dict[str, object]:
    """Create a text file through the public API."""
    payload: dict[str, object] = {"path": path, "content": content}
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    response = client.post("/api/v1/files/text", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_memory(
    client: TestClient,
    content: str,
    occurred_at: str,
    supersedes: list[int] | None = None,
) -> dict[str, object]:
    """Create a memory through the public API."""
    response = client.post(
        "/api/v1/memories",
        json={
            "content": content,
            "occurred_at": occurred_at,
            "supersedes": supersedes or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
