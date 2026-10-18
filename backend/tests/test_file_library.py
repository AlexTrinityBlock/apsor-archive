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

    # Text-only records have no stored original: the inline endpoint keeps the
    # existing domain error while the viewer falls back to indexed chunks.
    unavailable = client.get(f"/api/v1/files/{file_id}/content")
    assert unavailable.status_code == 404
    assert unavailable.json()["error"] == "file_content_unavailable"

    payload = b"Engine notes: intake, compression, ignition, exhaust.\n"
    uploaded = client.post(
        "/api/v1/files",
        data={"path": "/history/industry/engine.txt"},
        files={"file": ("engine.txt", payload, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    uploaded_id = int(uploaded.json()["id"])

    inline = client.get(f"/api/v1/files/{uploaded_id}/content")
    assert inline.status_code == 200
    assert inline.content == payload
    assert inline.headers["content-type"].startswith("text/plain")
    assert inline.headers["content-disposition"].startswith("inline")
    assert inline.headers["accept-ranges"] == "bytes"
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in inline.headers
    assert inline.headers["etag"].endswith('"')

    partial = client.get(
        f"/api/v1/files/{uploaded_id}/content",
        headers={"Range": "bytes=0-5"},
    )
    assert partial.status_code == 206
    assert partial.content == payload[:6]
    assert partial.headers["content-range"] == f"bytes 0-5/{len(payload)}"

    open_ended = client.get(
        f"/api/v1/files/{uploaded_id}/content",
        headers={"Range": "bytes=-8"},
    )
    assert open_ended.status_code == 206
    assert open_ended.content == payload[-8:]

    unsatisfiable = client.get(
        f"/api/v1/files/{uploaded_id}/content",
        headers={"Range": "bytes=9999-"},
    )
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == f"bytes */{len(payload)}"

    attachment = client.get(f"/api/v1/files/{uploaded_id}/download")
    assert attachment.status_code == 200
    assert attachment.content == payload
    assert attachment.headers["content-disposition"].startswith("attachment")
