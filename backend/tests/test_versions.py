"""Version branches and the default-hidden history behaviour."""

from fastapi.testclient import TestClient

from tests.helpers import create_text


def test_tree_history_and_versioning(client: TestClient) -> None:
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
        "/api/v1/tree",
        params={"root": "/versions", "depth": 3},
    )
    current_nodes = current.json()["nodes"]
    file_nodes = [node for node in current_nodes if node["kind"] == "file"]
    assert len(file_nodes) == 1
    assert file_nodes[0]["file_id"] == second_id

    history = client.get(
        "/api/v1/tree",
        params={"root": "/versions", "depth": 3, "include_history": True},
    )
    history_file_nodes = [
        node for node in history.json()["nodes"] if node["kind"] == "file"
    ]
    assert len(history_file_nodes) == 2
    old_node = next(node for node in history_file_nodes if node["file_id"] == first_id)
    assert old_node["is_current"] is False
    assert old_node["superseded_by_id"] is not None

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
