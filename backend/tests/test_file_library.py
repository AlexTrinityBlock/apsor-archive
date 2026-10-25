"""File ingestion, path listing, chunk windows, and soft deletion."""

import base64

from fastapi.testclient import TestClient

from tests.helpers import create_text

# A 1x1 blue PNG; enough to exercise the image extension and original storage.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_file_ingest_path_read_and_soft_delete(client: TestClient) -> None:
    content = "Automobile engineering notes. " * 300
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

    deleted_file = client.get(f"/api/v1/files/{file_id}")
    assert deleted_file.status_code == 200
    assert deleted_file.json()["deleted_at"] is not None
    assert deleted_file.json()["is_current"] is False
    after_delete_listing = client.get(
        "/api/v1/paths",
        params={"path": "/history", "path_depth": 5},
    )
    assert all(item["file_id"] != file_id for item in after_delete_listing.json()["files"])

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

    # Folder creation creates missing ancestors and is idempotent.
    folder = client.post(
        "/api/v1/folders",
        json={"path": "/history/workshop/engines"},
    )
    assert folder.status_code == 201, folder.text
    assert folder.json() == {
        "path": "/history/workshop/engines",
        "name": "engines",
        "depth": 3,
    }
    repeated_folder = client.post(
        "/api/v1/folders",
        json={"path": "/history/workshop/engines/"},
    )
    assert repeated_folder.status_code == 201
    assert repeated_folder.json() == folder.json()

    # Empty folders are explicit records, so a folder with no files still lists.
    workshop_listing = client.get(
        "/api/v1/paths",
        params={"path": "/history/workshop", "path_depth": 1},
    )
    assert workshop_listing.status_code == 200
    assert workshop_listing.json()["directories"] == [
        {
            "path": "/history/workshop/engines",
            "name": "engines",
            "depth": 3,
        }
    ]
    assert workshop_listing.json()["files"] == []

    deeper_listing = client.get(
        "/api/v1/paths",
        params={"path": "/history", "path_depth": 2},
    )
    deeper_paths = {item["path"] for item in deeper_listing.json()["directories"]}
    assert {
        "/history/workshop",
        "/history/workshop/engines",
    } <= deeper_paths

    invalid_folder = client.post("/api/v1/folders", json={"path": "/"})
    assert invalid_folder.status_code == 422
    assert invalid_folder.json()["error"] == "invalid_path"
    empty_folder = client.post("/api/v1/folders", json={"path": ""})
    assert empty_folder.status_code == 422
    assert empty_folder.json()["error"] == "invalid_path"
    folder_conflict = client.post(
        "/api/v1/folders",
        json={"path": "/history/industry/engine.txt"},
    )
    assert folder_conflict.status_code == 409
    assert folder_conflict.json()["error"] == "tree_path_conflict"

    # A move keeps the file id, version, chunks, and original bytes.
    moved = client.post(
        f"/api/v1/files/{uploaded_id}/move",
        json={"path": "/history/workshop/engines/engine.txt"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["id"] == uploaded_id
    assert moved.json()["version"] == 1
    assert moved.json()["raw_file_path"] == "/history/workshop/engines/engine.txt"

    old_listing = client.get(
        "/api/v1/paths",
        params={"path": "/history/industry", "path_depth": 1},
    )
    assert all(item["file_id"] != uploaded_id for item in old_listing.json()["files"])
    new_listing = client.get(
        "/api/v1/paths",
        params={"path": "/history/workshop/engines", "path_depth": 1},
    )
    assert any(item["file_id"] == uploaded_id for item in new_listing.json()["files"])
    moved_content = client.get(f"/api/v1/files/{uploaded_id}/content")
    assert moved_content.status_code == 200
    assert moved_content.content == payload

    same_move = client.post(
        f"/api/v1/files/{uploaded_id}/move",
        json={"path": "/history/workshop/engines/engine.txt"},
    )
    assert same_move.status_code == 200
    assert same_move.json()["raw_file_path"] == "/history/workshop/engines/engine.txt"
    extension_move = client.post(
        f"/api/v1/files/{uploaded_id}/move",
        json={"path": "/history/workshop/engines/engine.md"},
    )
    assert extension_move.status_code == 422
    assert extension_move.json()["error"] == "invalid_path"

    # A copy creates a new current file id at version 1 with fresh chunks.
    copied = client.post(
        f"/api/v1/files/{uploaded_id}/copy",
        json={"path": "/history/workshop/engines/engine-copy.txt"},
    )
    assert copied.status_code == 201, copied.text
    copied_id = int(copied.json()["id"])
    assert copied_id != uploaded_id
    assert copied.json()["version"] == 1
    assert copied.json()["is_current"] is True
    assert copied.json()["raw_file_path"] == "/history/workshop/engines/engine-copy.txt"
    assert copied.json()["has_original"] is True
    copied_content = client.get(f"/api/v1/files/{copied_id}/content")
    assert copied_content.status_code == 200
    assert copied_content.content == payload

    both_current = client.get(
        "/api/v1/paths",
        params={"path": "/history/workshop/engines", "path_depth": 1},
    )
    current_ids = {item["file_id"] for item in both_current.json()["files"]}
    assert {uploaded_id, copied_id} <= current_ids
    assert client.get(f"/api/v1/files/{uploaded_id}").json()["is_current"] is True
    assert client.get(f"/api/v1/files/{copied_id}").json()["is_current"] is True

    search = client.get(
        "/api/v1/search",
        params={"query": "compression", "result_number": 5},
    )
    assert search.status_code == 200
    searched_ids = {item["file_id"] for item in search.json()["file_results"]}
    assert copied_id in searched_ids

    # Text-only sources reconstruct their text from chunks without duplicating
    # the stored overlap, then re-chunk to the same boundaries.
    text_source = create_text(
        client,
        "/history/archive/notes.md",
        content,
        "2026-09-03T09:00:00Z",
    )
    text_copy = client.post(
        f"/api/v1/files/{int(text_source['id'])}/copy",
        json={"path": "/history/workshop/engines/notes-copy.md"},
    )
    assert text_copy.status_code == 201, text_copy.text
    assert text_copy.json()["has_original"] is False
    assert text_copy.json()["total_chunks"] == text_source["total_chunks"]
    source_window = client.get(
        f"/api/v1/files/{int(text_source['id'])}/chunks/1",
        params={"chunk_range": 1},
    )
    copy_window = client.get(
        f"/api/v1/files/{int(text_copy.json()['id'])}/chunks/1",
        params={"chunk_range": 1},
    )
    assert copy_window.json()["chunks"] == source_window.json()["chunks"]

    target_occupied = create_text(
        client,
        "/history/workshop/engines/reserved.txt",
        "Reserved for conflict checks.",
    )
    move_conflict = client.post(
        f"/api/v1/files/{uploaded_id}/move",
        json={"path": "/history/workshop/engines/reserved.txt"},
    )
    assert move_conflict.status_code == 409
    assert move_conflict.json()["error"] == "tree_path_conflict"
    copy_conflict = client.post(
        f"/api/v1/files/{uploaded_id}/copy",
        json={"path": "/history/workshop/engines/reserved.txt"},
    )
    assert copy_conflict.status_code == 409
    assert copy_conflict.json()["error"] == "tree_path_conflict"
    copy_extension = client.post(
        f"/api/v1/files/{uploaded_id}/copy",
        json={"path": "/history/workshop/engines/engine-copy.md"},
    )
    assert copy_extension.status_code == 422
    assert copy_extension.json()["error"] == "invalid_path"
    assert int(target_occupied["id"]) > copied_id

    # Durable async ingestion: the HTTP call only enqueues, a worker advances
    # the job through parsing/chunking/embedding, and the file becomes visible
    # only when the job publishes it.
    worker = client.app.state.ingest_worker
    assert worker.poll_seconds == 1.0
    assert worker.extract_workers == 2
    assert worker.max_in_flight_jobs == 2
    assert worker.embedding_concurrency == 6
    assert worker.extract_pool is not None
    assert worker.embedding_semaphore is not None
    assert client.app.state.settings.ingest_poll_seconds == 1.0
    assert client.app.state.settings.ingest_extract_workers == 2
    assert client.app.state.settings.ingest_max_inflight_jobs == 2
    assert client.app.state.settings.ingest_embedding_concurrency == 6

    async_text_path = "/history/async/quasar.md"
    async_text_content = "Quasar bearing maintenance guide. " * 220
    queued_text = client.post(
        "/api/v1/files/text/async",
        json={"path": async_text_path, "content": async_text_content},
    )
    assert queued_text.status_code == 202, queued_text.text
    text_job = queued_text.json()
    assert text_job["status"] == "queued"
    assert text_job["progress_pct"] == 0
    assert text_job["file_id"] is None
    assert text_job["chunks_total"] is None
    listed_jobs = client.get("/api/v1/files/ingest-jobs")
    assert listed_jobs.status_code == 200
    assert any(job["id"] == text_job["id"] for job in listed_jobs.json()["jobs"])

    not_ready = client.get(
        "/api/v1/search",
        params={"query": "quasar bearing", "result_number": 5},
    )
    assert not_ready.status_code == 200
    assert all(
        item["raw_file_path"] != async_text_path for item in not_ready.json()["file_results"]
    )

    assert client.portal is not None
    processed_text = client.portal.call(worker.process_job, text_job["id"])
    assert processed_text is not None
    assert processed_text.status == "ready"

    ready_text = client.get(f"/api/v1/files/ingest-jobs/{text_job['id']}")
    assert ready_text.status_code == 200
    text_state = ready_text.json()
    text_file_id = int(text_state["file_id"])
    assert text_state["status"] == "ready"
    assert text_state["progress_pct"] == 100
    assert int(text_state["chunks_total"]) >= 1
    assert text_state["chunks_embedded"] == text_state["chunks_total"]
    assert text_state["finished_at"] is not None
    assert text_state["error_code"] is None

    text_window = client.get(f"/api/v1/files/{text_file_id}/chunks/1")
    assert text_window.status_code == 200
    ready_search = client.get(
        "/api/v1/search",
        params={"query": "quasar bearing", "result_number": 5},
    )
    assert ready_search.status_code == 200
    assert any(item["file_id"] == text_file_id for item in ready_search.json()["file_results"])

    # The same queue drives uploaded originals; the original bytes keep the
    # inline viewer working after the job publishes.
    async_payload = b"Supercapacitor calibration notes for the workshop.\n" * 120
    queued_upload = client.post(
        "/api/v1/files/async",
        data={"path": "/history/async/supercapacitor.txt"},
        files={"file": ("supercapacitor.txt", async_payload, "text/plain")},
    )
    assert queued_upload.status_code == 202, queued_upload.text
    upload_job = queued_upload.json()
    assert upload_job["source_kind"] == "upload"
    assert upload_job["file_id"] is None
    assert client.portal.call(worker.run_once) is True
    upload_state = client.get(f"/api/v1/files/ingest-jobs/{upload_job['id']}").json()
    assert upload_state["status"] == "ready"
    assert upload_state["chunks_embedded"] == upload_state["chunks_total"]
    upload_content = client.get(f"/api/v1/files/{int(upload_state['file_id'])}/content")
    assert upload_content.status_code == 200
    assert upload_content.content == async_payload

    # Failed extraction keeps the job readable and never publishes a partial
    # current file or chunks.
    broken = client.post(
        "/api/v1/files/async",
        data={"path": "/history/async/broken.pdf"},
        files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")},
    )
    assert broken.status_code == 202, broken.text
    broken_job = broken.json()
    assert client.portal.call(worker.process_job, broken_job["id"]) is not None
    broken_state = client.get(f"/api/v1/files/ingest-jobs/{broken_job['id']}").json()
    assert broken_state["status"] == "failed"
    assert broken_state["error_code"] == "empty_content"
    assert broken_state["error_detail"]
    assert broken_state["file_id"] is None
    assert broken_state["progress_pct"] < 100
    after_failure = client.get(
        "/api/v1/paths",
        params={"path": "/history/async", "path_depth": 1},
    )
    assert after_failure.status_code == 200
    assert all(
        item["raw_file_path"] != "/history/async/broken.pdf"
        for item in after_failure.json()["files"]
    )

    # The synchronous endpoints still return a fully indexed file.
    sync_text = create_text(
        client,
        "/history/async/sync.md",
        "Synchronous ingestion still works. " * 80,
    )
    assert int(sync_text["total_chunks"]) >= 1

    # Ingestion runtime settings live in a singleton row and start from the
    # environment-seeded defaults when the fresh test database has no row.
    ingest_settings = client.get("/api/v1/settings/ingest")
    assert ingest_settings.status_code == 200, ingest_settings.text
    ingest_body = ingest_settings.json()
    assert ingest_body["source"] == "default"
    ingest_defaults = ingest_body["defaults"]
    assert ingest_defaults == {
        "poll_seconds": 1.0,
        "extract_workers": 2,
        "max_inflight_jobs": 2,
        "embedding_concurrency": 6,
        "chunk_target_chars": 4_000,
        "chunk_overlap_chars": 500,
    }
    assert ingest_body["config"] == ingest_defaults
    assert ingest_body["updated_at"] is not None

    invalid_ingest = client.put(
        "/api/v1/settings/ingest",
        json={**ingest_defaults, "chunk_overlap_chars": 4_000},
    )
    assert invalid_ingest.status_code == 400
    assert invalid_ingest.json()["error"] == "invalid_request"
    assert "chunk_overlap_chars" in invalid_ingest.json()["detail"]

    non_default_ingest = {
        **ingest_defaults,
        "poll_seconds": 2.5,
        "extract_workers": 4,
        "max_inflight_jobs": 3,
        "embedding_concurrency": 12,
        "chunk_target_chars": 8_000,
        "chunk_overlap_chars": 1_000,
    }
    stored_ingest = client.put(
        "/api/v1/settings/ingest",
        json=non_default_ingest,
    )
    assert stored_ingest.status_code == 200, stored_ingest.text
    stored_ingest_body = stored_ingest.json()
    assert stored_ingest_body["source"] == "database"
    assert stored_ingest_body["config"] == non_default_ingest
    assert stored_ingest_body["updated_at"] is not None

    persisted_ingest = client.get("/api/v1/settings/ingest")
    assert persisted_ingest.status_code == 200
    assert persisted_ingest.json()["source"] == "database"
    assert persisted_ingest.json()["config"] == non_default_ingest

    reset_ingest = client.post("/api/v1/settings/ingest/reset")
    assert reset_ingest.status_code == 200, reset_ingest.text
    reset_ingest_body = reset_ingest.json()
    assert reset_ingest_body["source"] == "database"
    assert reset_ingest_body["config"] == ingest_defaults

    # Images are normal files even when no vision provider is configured.
    uploaded_image = client.post(
        "/api/v1/files",
        data={"path": "/images/blue-square.png"},
        files={"file": ("blue-square.png", BLUE_PNG, "image/png")},
    )
    assert uploaded_image.status_code == 201, uploaded_image.text
    image = uploaded_image.json()
    image_id = int(image["id"])
    assert image["document_type"] == "image"
    assert image["extraction_method"] == "filename"
    assert image["has_original"] is True
    assert int(image["total_chunks"]) >= 1

    image_content = client.get(f"/api/v1/files/{image_id}/content")
    assert image_content.status_code == 200
    assert image_content.content == BLUE_PNG
    assert image_content.headers["content-type"].startswith("image/png")

    image_chunks = client.get(f"/api/v1/files/{image_id}/chunks/1")
    assert image_chunks.status_code == 200
    assert "blue square image" in image_chunks.json()["chunks"][0]["content"]

    image_listing = client.get(
        "/api/v1/paths",
        params={"path": "/images", "path_depth": 1},
    )
    assert image_listing.status_code == 200
    assert [item["file_id"] for item in image_listing.json()["files"]] == [image_id]

    image_search = client.get(
        "/api/v1/search",
        params={"query": "blue square", "result_number": 5},
    )
    assert image_search.status_code == 200
    assert any(item["file_id"] == image_id for item in image_search.json()["file_results"])
