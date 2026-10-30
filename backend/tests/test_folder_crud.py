"""Folder rename, move, copy, and recursive delete through the public API."""

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.knowledge.service import file_service
from tests.helpers import create_text

# A 1x1 blue PNG; the upload path must preserve these exact bytes in a copy.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# The existing router exposes the deleteLibrarySelection operation here.
DELETE_SELECTION_URL = "/api/v1/files/batch-delete"


def _create_folder(client: TestClient, path: str) -> None:
    response = client.post("/api/v1/folders", json={"path": path})
    assert response.status_code == 201, response.text


def _listing(client: TestClient, path: str, *, depth: int = 1) -> dict[str, Any]:
    response = client.get(
        "/api/v1/paths",
        params={"path": path, "path_depth": depth},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _file_ids(listing: dict[str, Any]) -> set[int]:
    return {int(item["file_id"]) for item in listing["files"]}


def _upload(
    client: TestClient,
    path: str,
    data: bytes,
    content_type: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/files",
        data={"path": path},
        files={"file": (path.rsplit("/", 1)[-1], data, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _chunks(client: TestClient, file_id: int) -> list[dict[str, Any]]:
    detail = client.get(f"/api/v1/files/{file_id}")
    assert detail.status_code == 200, detail.text
    total = int(detail.json()["total_chunks"])
    assert total <= 26
    response = client.get(
        f"/api/v1/files/{file_id}/chunks/1",
        params={"chunk_range": 25},
    )
    assert response.status_code == 200, response.text
    chunks = response.json()["chunks"]
    assert len(chunks) == total
    return chunks


def _content(client: TestClient, file_id: int) -> bytes:
    response = client.get(f"/api/v1/files/{file_id}/content")
    assert response.status_code == 200, response.text
    return response.content


def _search_file_ids(client: TestClient, query: str) -> set[int]:
    response = client.get(
        "/api/v1/search",
        params={"query": query, "result_number": 10},
    )
    assert response.status_code == 200, response.text
    return {int(item["file_id"]) for item in response.json()["file_results"]}


def test_folder_rename_updates_subtree_files_and_conflicts(client: TestClient) -> None:
    """Rename moves the whole subtree and its current leaves, preserving file identity."""
    _create_folder(client, "/projects/alpha")
    _create_folder(client, "/projects/alpha/child")
    _create_folder(client, "/projects/alpha/empty")
    first = create_text(client, "/projects/alpha/plan.md", "Alpha plan. " * 40)
    second = create_text(
        client,
        "/projects/alpha/child/notes.md",
        "Alpha child notes. " * 40,
    )
    first_id = int(first["id"])
    second_id = int(second["id"])
    first_chunks = _chunks(client, first_id)

    response = client.post(
        "/api/v1/folders/rename",
        json={"path": "/projects/alpha", "new_name": "beta"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["folder"] == {"path": "/projects/beta", "name": "beta", "depth": 2}
    assert body["affected_folders"] == 3
    assert body["affected_files"] == 2

    projects = _listing(client, "/projects")
    assert {item["path"] for item in projects["directories"]} == {"/projects/beta"}
    assert projects["files"] == []

    beta = _listing(client, "/projects/beta")
    assert {item["path"] for item in beta["directories"]} == {
        "/projects/beta/child",
        "/projects/beta/empty",
    }
    assert _file_ids(beta) == {first_id}

    child = _listing(client, "/projects/beta/child")
    assert _file_ids(child) == {second_id}

    # Identity, version, chunks, and the final file name survive the rename.
    first_detail = client.get(f"/api/v1/files/{first_id}")
    assert first_detail.status_code == 200
    first_body = first_detail.json()
    assert first_body["raw_file_path"] == "/projects/beta/plan.md"
    assert first_body["file_name"] == "plan.md"
    assert first_body["version"] == first["version"]
    assert first_body["total_chunks"] == first["total_chunks"]
    assert _chunks(client, first_id) == first_chunks

    second_detail = client.get(f"/api/v1/files/{second_id}")
    assert second_detail.status_code == 200
    assert second_detail.json()["raw_file_path"] == "/projects/beta/child/notes.md"

    # The old paths are gone from the tree, including the former child path.
    assert client.get("/api/v1/paths", params={"path": "/projects/alpha"}).status_code == 404
    assert (
        client.get("/api/v1/paths", params={"path": "/projects/alpha/child"}).status_code
        == 404
    )

    # Renaming onto an existing sibling folder is a stable conflict.
    _create_folder(client, "/projects/gamma")
    conflict = client.post(
        "/api/v1/folders/rename",
        json={"path": "/projects/beta", "new_name": "gamma"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "tree_path_conflict"

    # The root itself can never be renamed.
    root = client.post(
        "/api/v1/folders/rename",
        json={"path": "/", "new_name": "root"},
    )
    assert root.status_code == 422
    assert root.json()["error"] == "invalid_path"

    # Failed operations leave the successful rename untouched.
    assert _file_ids(_listing(client, "/projects/beta")) == {first_id}
    assert _file_ids(_listing(client, "/projects/beta/child")) == {second_id}


def test_folder_move_rejects_descendant_and_keeps_file_identity(client: TestClient) -> None:
    """Move relocates the subtree and leaves file rows, versions, and chunks untouched."""
    _create_folder(client, "/projects/beta")
    _create_folder(client, "/projects/beta/child")
    _create_folder(client, "/projects/beta/empty")
    first = create_text(client, "/projects/beta/plan.md", "Move plan. " * 60)
    second = create_text(client, "/projects/beta/child/notes.md", "Move child. " * 60)
    first_id = int(first["id"])
    second_id = int(second["id"])
    first_chunks = _chunks(client, first_id)
    second_chunks = _chunks(client, second_id)

    response = client.post(
        "/api/v1/folders/move",
        json={"path": "/projects/beta", "target_path": "/archive/2026/beta"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["folder"] == {"path": "/archive/2026/beta", "name": "beta", "depth": 3}
    assert body["affected_folders"] == 3
    assert body["affected_files"] == 2

    # Missing destination ancestors are created as real folder rows.
    archive = _listing(client, "/archive")
    assert {item["path"] for item in archive["directories"]} == {"/archive/2026"}
    year = _listing(client, "/archive/2026")
    assert {item["path"] for item in year["directories"]} == {"/archive/2026/beta"}

    moved = _listing(client, "/archive/2026/beta")
    assert {item["path"] for item in moved["directories"]} == {
        "/archive/2026/beta/child",
        "/archive/2026/beta/empty",
    }
    assert _file_ids(moved) == {first_id}
    assert _file_ids(_listing(client, "/archive/2026/beta/child")) == {second_id}
    empty = next(
        item for item in moved["directories"] if item["path"] == "/archive/2026/beta/empty"
    )
    assert empty["depth"] == 4

    first_detail = client.get(f"/api/v1/files/{first_id}")
    assert first_detail.status_code == 200
    first_body = first_detail.json()
    assert first_body["raw_file_path"] == "/archive/2026/beta/plan.md"
    assert first_body["version"] == first["version"]
    assert first_body["total_chunks"] == first["total_chunks"]
    assert _chunks(client, first_id) == first_chunks

    second_detail = client.get(f"/api/v1/files/{second_id}")
    assert second_detail.status_code == 200
    assert second_detail.json()["raw_file_path"] == "/archive/2026/beta/child/notes.md"
    assert second_detail.json()["version"] == second["version"]
    assert _chunks(client, second_id) == second_chunks

    # Moving a folder onto its own current path is an explicit no-op.
    no_op = client.post(
        "/api/v1/folders/move",
        json={"path": "/archive/2026/beta", "target_path": "/archive/2026/beta"},
    )
    assert no_op.status_code == 200
    assert no_op.json()["affected_folders"] == 0
    assert no_op.json()["affected_files"] == 0

    # A destination inside the moved subtree would make the tree its own parent.
    inside = client.post(
        "/api/v1/folders/move",
        json={
            "path": "/archive/2026/beta",
            "target_path": "/archive/2026/beta/child/moved",
        },
    )
    assert inside.status_code == 422
    assert inside.json()["error"] == "invalid_path"

    # An existing destination folder is a conflict, not an overwrite.
    _create_folder(client, "/archive/2026/occupied")
    conflict = client.post(
        "/api/v1/folders/move",
        json={"path": "/archive/2026/beta", "target_path": "/archive/2026/occupied"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "tree_path_conflict"

    # The rejected operations leave the original move intact.
    assert _file_ids(_listing(client, "/archive/2026/beta")) == {first_id}
    assert _file_ids(_listing(client, "/archive/2026/beta/child")) == {second_id}


def test_folder_copy_clones_tree_originals_and_chunks(client: TestClient) -> None:
    """Copy recreates folders, empty folders, originals, and chunk rows at new ids."""
    _create_folder(client, "/projects/beta")
    _create_folder(client, "/projects/beta/nested")
    _create_folder(client, "/projects/beta/empty")
    text_content = "Cloned retrieval notes. " * 400
    source_text = create_text(client, "/projects/beta/notes.md", text_content)
    source_binary = _upload(
        client,
        "/projects/beta/nested/pixel.png",
        BLUE_PNG,
        "image/png",
    )
    source_text_id = int(source_text["id"])
    source_binary_id = int(source_binary["id"])
    source_ids = {source_text_id, source_binary_id}
    assert int(source_text["total_chunks"]) >= 2

    source_chunks = {file_id: _chunks(client, file_id) for file_id in source_ids}
    source_bytes = {file_id: _content(client, file_id) for file_id in source_ids}

    response = client.post(
        "/api/v1/folders/copy",
        json={"path": "/projects/beta", "target_path": "/backup/beta-copy"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["folder"] == {
        "path": "/backup/beta-copy",
        "name": "beta-copy",
        "depth": 2,
    }
    assert body["affected_folders"] == 3
    assert body["affected_files"] == 2

    backup = _listing(client, "/backup")
    assert {item["path"] for item in backup["directories"]} == {"/backup/beta-copy"}
    copy_root = _listing(client, "/backup/beta-copy")
    assert {item["path"] for item in copy_root["directories"]} == {
        "/backup/beta-copy/nested",
        "/backup/beta-copy/empty",
    }
    assert {item["file_name"] for item in copy_root["files"]} == {"notes.md"}
    copy_nested = _listing(client, "/backup/beta-copy/nested")
    assert {item["file_name"] for item in copy_nested["files"]} == {"pixel.png"}

    # The empty source folder is a real folder row in the copied tree.
    copied_empty = _listing(client, "/backup/beta-copy/empty")
    assert copied_empty["directories"] == []
    assert copied_empty["files"] == []

    copied_ids: dict[str, int] = {}
    for item in [*copy_root["files"], *copy_nested["files"]]:
        copied_ids[str(item["file_name"])] = int(item["file_id"])
    assert set(copied_ids) == {"notes.md", "pixel.png"}
    assert set(copied_ids.values()).isdisjoint(source_ids)

    source_by_name = {"notes.md": source_text_id, "pixel.png": source_binary_id}
    expected_paths = {
        "notes.md": "/backup/beta-copy/notes.md",
        "pixel.png": "/backup/beta-copy/nested/pixel.png",
    }
    for name, copied_id in copied_ids.items():
        source_id = source_by_name[name]
        copied_detail = client.get(f"/api/v1/files/{copied_id}")
        assert copied_detail.status_code == 200, copied_detail.text
        copied_body = copied_detail.json()
        assert copied_body["raw_file_path"] == expected_paths[name]
        assert copied_body["version"] == 1
        assert copied_body["supersedes_file_id"] is None
        assert copied_body["has_original"] is True
        assert copied_body["total_chunks"] == len(source_chunks[source_id])
        assert _content(client, copied_id) == source_bytes[source_id]
        assert _chunks(client, copied_id) == source_chunks[source_id]

    # Copying never mutates the source tree, its ids, bytes, or chunks.
    assert _file_ids(_listing(client, "/projects/beta")) == {source_text_id}
    assert _file_ids(_listing(client, "/projects/beta/nested")) == {source_binary_id}
    for source_id in source_ids:
        assert _content(client, source_id) == source_bytes[source_id]
        assert _chunks(client, source_id) == source_chunks[source_id]


def test_folder_copy_rejects_collision_inside_self_and_oversize(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copy fails closed on occupied targets, self-nesting, and the size guard."""
    _create_folder(client, "/copy-source/report")
    _create_folder(client, "/copy-source/report/child")
    first = create_text(client, "/copy-source/report/one.md", "Copy guard one. " * 30)
    second = create_text(
        client,
        "/copy-source/report/child/two.md",
        "Copy guard two. " * 30,
    )
    first_id = int(first["id"])
    second_id = int(second["id"])

    # An existing folder at the destination is a conflict.
    _create_folder(client, "/copy-target/report")
    collision = client.post(
        "/api/v1/folders/copy",
        json={"path": "/copy-source/report", "target_path": "/copy-target/report"},
    )
    assert collision.status_code == 409
    assert collision.json()["error"] == "tree_path_conflict"
    assert client.get("/api/v1/paths", params={"path": "/copy-target/report"}).status_code == 200

    # A current file occupying the destination folder path is also a conflict.
    create_text(client, "/copy-target/reserved.md", "Reserved copy target.")
    file_collision = client.post(
        "/api/v1/folders/copy",
        json={"path": "/copy-source/report", "target_path": "/copy-target/reserved.md"},
    )
    assert file_collision.status_code == 409
    assert file_collision.json()["error"] == "tree_path_conflict"

    # A copy destination below the source would recursively contain itself.
    inside = client.post(
        "/api/v1/folders/copy",
        json={
            "path": "/copy-source/report",
            "target_path": "/copy-source/report/child/inside",
        },
    )
    assert inside.status_code == 422
    assert inside.json()["error"] == "invalid_path"

    # The file-count guard rejects before creating any folder or file row.
    monkeypatch.setattr(file_service, "FOLDER_COPY_MAX_FILES", 1)
    oversize = client.post(
        "/api/v1/folders/copy",
        json={"path": "/copy-source/report", "target_path": "/copy-target/too-large"},
    )
    assert oversize.status_code == 422
    assert oversize.json()["error"] == "folder_copy_too_large"
    assert client.get("/api/v1/paths", params={"path": "/copy-target/too-large"}).status_code == 404
    target = _listing(client, "/copy-target")
    assert {item["path"] for item in target["directories"]} == {"/copy-target/report"}
    assert {item["file_name"] for item in target["files"]} == {"reserved.md"}

    # The source remains complete after every rejected operation.
    assert _file_ids(_listing(client, "/copy-source/report")) == {first_id}
    assert _file_ids(_listing(client, "/copy-source/report/child")) == {second_id}


def test_folder_copy_promotes_legacy_text_only_original(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A copied legacy chunk-only file gains a readable stored original."""
    _create_folder(client, "/legacy/source")
    content = "Windmill brake maintenance notes for the legacy archive."
    created = create_text(client, "/legacy/source/legacy-note.md", content)
    file_id = int(created["id"])
    chunks = _chunks(client, file_id)
    assert _content(client, file_id) == content.encode("utf-8")

    # Simulate a legacy row written before originals were mandatory.
    with owner_engine.begin() as connection:
        updated = connection.execute(
            text(
                "UPDATE file SET storage_key = NULL, storage_backend = NULL "
                "WHERE id = :file_id"
            ),
            {"file_id": file_id},
        )
        assert updated.rowcount == 1

    legacy = client.get(f"/api/v1/files/{file_id}")
    assert legacy.status_code == 200
    assert legacy.json()["has_original"] is False
    unavailable = client.get(f"/api/v1/files/{file_id}/content")
    assert unavailable.status_code == 404
    assert unavailable.json()["error"] == "file_content_unavailable"

    response = client.post(
        "/api/v1/folders/copy",
        json={"path": "/legacy/source", "target_path": "/legacy/copied"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["affected_folders"] == 1
    assert body["affected_files"] == 1

    copied_listing = _listing(client, "/legacy/copied")
    assert len(copied_listing["files"]) == 1
    copied_id = int(copied_listing["files"][0]["file_id"])
    assert copied_id != file_id

    copied = client.get(f"/api/v1/files/{copied_id}")
    assert copied.status_code == 200
    copied_body = copied.json()
    assert copied_body["has_original"] is True
    assert copied_body["total_chunks"] == len(chunks)
    assert _content(client, copied_id).decode("utf-8") == content
    assert _chunks(client, copied_id) == chunks

    # Promotion is confined to the copy; the source row stays legacy.
    assert client.get(f"/api/v1/files/{file_id}").json()["has_original"] is False
    assert client.get(f"/api/v1/files/{file_id}/content").status_code == 404


def test_folder_delete_recurses_soft_deletes_and_retains_originals(
    client: TestClient,
) -> None:
    """Selecting a folder soft-deletes its current files, removes its rows, and hides hits."""
    _create_folder(client, "/trash/target")
    _create_folder(client, "/trash/target/child")
    first_content = "Airship maintenance log. " * 40
    second_content = "Airship archive record. " * 40
    first = create_text(client, "/trash/target/one.md", first_content)
    second = create_text(client, "/trash/target/child/two.md", second_content)
    keep_content = "Lighthouse keeper notes. " * 40
    keep = create_text(client, "/trash/keep.md", keep_content)
    first_id = int(first["id"])
    second_id = int(second["id"])
    keep_id = int(keep["id"])
    deleted_ids = {first_id, second_id}

    assert deleted_ids <= _search_file_ids(client, "airship")

    response = client.post(
        DELETE_SELECTION_URL,
        json={"folder_paths": ["/trash/target"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted_folder_paths"] == ["/trash/target"]
    assert body["deleted_folders"] == 2
    assert body["deleted_files"] == 2
    assert set(body["deleted_file_ids"]) == deleted_ids

    # Folder rows are hard-deleted for the selected subtree.
    assert client.get("/api/v1/paths", params={"path": "/trash/target"}).status_code == 404
    assert (
        client.get("/api/v1/paths", params={"path": "/trash/target/child"}).status_code
        == 404
    )
    trash = _listing(client, "/trash")
    assert trash["directories"] == []
    assert _file_ids(trash) == {keep_id}

    # File rows stay as non-current history, and their original bytes remain readable.
    for file_id, expected_content in (
        (first_id, first_content),
        (second_id, second_content),
    ):
        detail = client.get(f"/api/v1/files/{file_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["is_current"] is False
        assert detail_body["deleted_at"] is not None
        assert _content(client, file_id) == expected_content.encode("utf-8")
        window = client.get(
            f"/api/v1/files/{file_id}/chunks/1",
            params={"chunk_range": 1},
        )
        assert window.status_code == 200
        assert window.json()["chunks"]
        assert all(chunk["is_current"] is False for chunk in window.json()["chunks"])

    # Deleted files disappear from default search; another branch is unaffected.
    assert _search_file_ids(client, "airship").isdisjoint(deleted_ids)
    assert keep_id in _search_file_ids(client, "lighthouse")
    keep_detail = client.get(f"/api/v1/files/{keep_id}")
    assert keep_detail.status_code == 200
    assert keep_detail.json()["is_current"] is True
    assert _content(client, keep_id) == keep_content.encode("utf-8")
