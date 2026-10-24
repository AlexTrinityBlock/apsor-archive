"""Version branches and the default-hidden history behaviour."""

from fastapi.testclient import TestClient

from tests.helpers import create_text


def test_file_history_and_versioning(client: TestClient) -> None:
    first = create_text(
        client,
        "/versions/document.md",
        "Alpha content for the first version.",
        "2026-09-05T09:00:00Z",
    )
    first_id = int(first["id"])
    second = create_text(
        client,
        "/versions/document.md",
        "Beta content for the second version.",
        "2026-09-06T09:00:00Z",
    )
    second_id = int(second["id"])

    assert second_id > first_id
    assert second["version"] == 2
    assert second["supersedes_file_id"] == first_id

    current = client.get(
        "/api/v1/paths",
        params={"path": "/versions", "path_depth": 1},
    )
    current_ids = [item["file_id"] for item in current.json()["files"]]
    assert current_ids == [second_id]

    old_version = client.get(f"/api/v1/files/{first_id}")
    assert old_version.status_code == 200
    assert old_version.json()["is_current"] is False
    assert old_version.json()["deleted_at"] is None

    old_search = client.get(
        "/api/v1/search",
        params={"query": "alpha", "result_number": 2},
    )
    old_ids = {item["file_id"] for item in old_search.json()["file_results"]}
    assert first_id not in old_ids

    new_search = client.get(
        "/api/v1/search",
        params={"query": "beta", "result_number": 2},
    )
    new_ids = {item["file_id"] for item in new_search.json()["file_results"]}
    assert second_id in new_ids
