"""Verify versioned Markdown content updates through the public file API."""

from fastapi.testclient import TestClient

from tests.helpers import create_text


def test_update_markdown_creates_new_version_and_reindexes(client: TestClient) -> None:
    original_content = (
        "# Maintenance plan\n\nReplace the legacy tractor filter every 500 operating hours.\n"
    )
    created = create_text(client, "/notes/plan.md", original_content)
    original_file_id = int(created["id"])
    assert created["version"] == 1
    assert created["is_current"] is True
    assert created["has_original"] is True
    assert created["supersedes_file_id"] is None

    # Text creation stores the exact bytes, including blank lines, so the inline
    # reader and the editor do not need to reconstruct the content from chunks.
    original_content_response = client.get(f"/api/v1/files/{original_file_id}/content")
    assert original_content_response.status_code == 200
    assert original_content_response.content.decode("utf-8") == original_content

    before_update = client.get(
        "/api/v1/paths",
        params={"path": "/notes", "path_depth": 1},
    )
    assert before_update.status_code == 200
    assert [item["file_id"] for item in before_update.json()["files"]] == [original_file_id]
    assert before_update.json()["files"][0]["has_original"] is True

    updated_content = (
        "# Maintenance plan\n\nRecalibrate the combine harvester sensor before the harvest season."
    )
    response = client.put(
        f"/api/v1/files/{original_file_id}/content",
        json={"content": updated_content, "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    updated_file_id = int(updated["id"])
    assert updated_file_id != original_file_id
    assert updated["raw_file_path"] == "/notes/plan.md"
    assert updated["version"] == 2
    assert updated["supersedes_file_id"] == original_file_id
    assert updated["is_current"] is True
    assert updated["has_original"] is True

    old_file = client.get(f"/api/v1/files/{original_file_id}")
    assert old_file.status_code == 200
    assert old_file.json()["is_current"] is False

    new_content = client.get(f"/api/v1/files/{updated_file_id}/content")
    assert new_content.status_code == 200
    assert new_content.content.decode("utf-8") == updated_content

    chunks = client.get(
        f"/api/v1/files/{updated_file_id}/chunks/1",
        params={"chunk_range": 1},
    )
    assert chunks.status_code == 200, chunks.text
    indexed_text = "\n".join(item["content"] for item in chunks.json()["chunks"])
    assert "combine harvester sensor" in indexed_text
    assert "legacy tractor" not in indexed_text

    # The current version has a stored original, and the listing shows only it.
    listing = client.get(
        "/api/v1/paths",
        params={"path": "/notes", "path_depth": 1},
    )
    assert listing.status_code == 200
    assert [item["file_id"] for item in listing.json()["files"]] == [updated_file_id]
    assert listing.json()["files"][0]["has_original"] is True


def test_update_markdown_rejects_stale_version(client: TestClient) -> None:
    created = create_text(client, "/notes/stale.md", "# Stale\n\nFirst revision.")
    file_id = int(created["id"])

    response = client.put(
        f"/api/v1/files/{file_id}/content",
        json={
            "content": "# Stale\n\nConflicting revision.",
            "expected_version": 99,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == "file_version_conflict"

    unchanged = client.get(f"/api/v1/files/{file_id}")
    assert unchanged.status_code == 200
    assert unchanged.json()["version"] == 1
    assert unchanged.json()["is_current"] is True


def test_update_markdown_rejects_non_markdown(client: TestClient) -> None:
    created = create_text(client, "/notes/plain.txt", "Plain text stays read-only.")
    file_id = int(created["id"])

    response = client.put(
        f"/api/v1/files/{file_id}/content",
        json={"content": "An attempted text update.", "expected_version": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_file_type"


def test_update_markdown_rejects_deleted_or_history_file(client: TestClient) -> None:
    created = create_text(client, "/notes/versioned.md", "# Versioned\n\nFirst body.")
    original_file_id = int(created["id"])

    updated = client.put(
        f"/api/v1/files/{original_file_id}/content",
        json={"content": "# Versioned\n\nSecond body.", "expected_version": 1},
    )
    assert updated.status_code == 200, updated.text
    updated_file_id = int(updated.json()["id"])

    history_update = client.put(
        f"/api/v1/files/{original_file_id}/content",
        json={"content": "# Versioned\n\nIgnored body.", "expected_version": 1},
    )
    assert history_update.status_code == 404
    assert history_update.json()["error"] == "file_not_found"

    # DELETE only accepts a current file; a DELETE against a historical version id
    # must also return 404.
    history_delete = client.delete(f"/api/v1/files/{original_file_id}")
    assert history_delete.status_code == 404
    assert history_delete.json()["error"] == "file_not_found"

    deleted = client.delete(f"/api/v1/files/{updated_file_id}")
    assert deleted.status_code == 204

    deleted_update = client.put(
        f"/api/v1/files/{updated_file_id}/content",
        json={"content": "# Versioned\n\nThird body.", "expected_version": 2},
    )
    assert deleted_update.status_code == 404
    assert deleted_update.json()["error"] == "file_not_found"


def test_update_markdown_rejects_empty_content(client: TestClient) -> None:
    created = create_text(client, "/notes/empty.md", "# Empty\n\nNon-empty source.")
    file_id = int(created["id"])

    response = client.put(
        f"/api/v1/files/{file_id}/content",
        json={"content": "", "expected_version": 1},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "content" in body["detail"]


def test_update_markdown_rejects_oversized_schema_content(client: TestClient) -> None:
    """The schema's max_length must reject oversized content before it reaches the service."""
    created = create_text(client, "/notes/oversized.md", "# Oversized\n\nSmall source.")
    file_id = int(created["id"])

    response = client.put(
        f"/api/v1/files/{file_id}/content",
        json={"content": "x" * 2_000_001, "expected_version": 1},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_request"
    detail = body["detail"]
    # This is a Pydantic length validation error, not the service's byte-limit error.
    assert "content" in detail
    assert "2000000" in detail
    assert "file_too_large" not in response.text

    # The request was rejected at the schema stage, so neither the file version
    # nor its content may change.
    unchanged = client.get(f"/api/v1/files/{file_id}")
    assert unchanged.status_code == 200
    assert unchanged.json()["version"] == 1
    assert unchanged.json()["is_current"] is True
