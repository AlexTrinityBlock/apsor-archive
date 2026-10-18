"""File ingestion, path listing, chunk windows, and soft deletion."""

from fastapi.testclient import TestClient

from tests.helpers import create_text


def test_file_ingest_path_read_and_soft_delete(client: TestClient) -> None:
    content = "Automobile engineering notes. " * 80
    created = create_text(
        client,
        "/history/industry/car.md",
        content,
        "2026-09-01T09:00:00Z",
    )
    file_id = int(created["id"])
    assert int(created["total_chunks"]) >= 2

    listing = client.get(
        "/api/v1/paths",
        params={"path": "/history/industry", "path_depth": 1},
    )
    assert listing.status_code == 200
    assert any(item["file_id"] == file_id for item in listing.json()["files"])

    window = client.get(
        f"/api/v1/files/{file_id}/chunks/1",
        params={"chunk_range": 1},
    )
    assert window.status_code == 200
    body = window.json()
    assert body["chunk_start"] == 1
    assert body["chunk_end"] == 2
    assert body["chunks"][0]["chunk"] == 1

    tool = client.get(
        "/api/v1/tools/read_file",
        params={"file_id": file_id, "chunk": 1, "chunk_range": 1},
    )
    assert tool.status_code == 200
    assert "<result" in tool.text
    assert '<chunk index="1"' in tool.text

    deleted = client.delete(f"/api/v1/files/{file_id}")
    assert deleted.status_code == 204

    current_tree = client.get("/api/v1/tree", params={"root": "/history", "depth": 5})
    current_nodes = current_tree.json()["nodes"]
    assert all(node["file_id"] != file_id for node in current_nodes)

    history_tree = client.get(
        "/api/v1/tree",
        params={"root": "/history", "depth": 5, "include_history": True},
    )
    history_nodes = history_tree.json()["nodes"]
    deleted_nodes = [node for node in history_nodes if node["file_id"] == file_id]
    assert deleted_nodes and deleted_nodes[0]["deleted_at"] is not None

    recreated = create_text(
        client,
        "/history/industry/car.md",
        "A new edition of the automobile notes.",
        "2026-09-02T09:00:00Z",
    )
    assert int(recreated["id"]) > file_id
    assert recreated["version"] == 1
