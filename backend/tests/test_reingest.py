"""Vision re-ingest: versioning, source safety, validation, and race handling."""

import base64
from typing import Literal

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.ai.vision_extractor import NullVisionExtractor
from app.module.knowledge.dependencies import (
    ingest_runtime_defaults,
    load_ingest_runtime_config,
)
from app.module.knowledge.domain.vision_prompt_domain import (
    VISION_LANGUAGE_PLACEHOLDER,
    render_vision_prompt,
)
from app.module.knowledge.exception.domain_error import VisionExtractionError
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument
from tests.helpers import create_text

# A 1x1 blue PNG; enough to exercise the image extension and shared original bytes.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

DESCRIPTION = "A white receipt on a blue table with a red square."
TABLE = "| Item | Price |\n|---|---|\n| Widget | 42 |"


def _prompt(label: str) -> str:
    """Build a valid template that mentions every required output key."""
    return (
        f"{label}. Return one JSON object with the keys text, tables, description, "
        f"caption, title, summary, document_type, tags, and language. "
        f"Use {VISION_LANGUAGE_PLACEHOLDER} for description, caption, title, summary, "
        "and tags. Keep OCR text verbatim. Do not translate. "
        "Use GitHub-Flavored Markdown tables."
    )


def _save_prompts(
    client: TestClient,
    image_prompt: str,
    document_prompt: str,
) -> None:
    response = client.put(
        "/api/v1/settings/ingest/vision-prompts",
        json={"image_prompt": image_prompt, "document_prompt": document_prompt},
    )
    assert response.status_code == 200, response.text


def _upload_image(client: TestClient, path: str) -> dict[str, object]:
    uploaded = client.post(
        "/api/v1/files",
        data={"path": path},
        files={"file": (path.rsplit("/", 1)[-1], BLUE_PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return uploaded.json()


def _enqueue(client: TestClient, file_id: int, expected_version: int):
    return client.post(
        f"/api/v1/files/{file_id}/reingest",
        json={"expected_version": expected_version},
    )


def _chunk_text(client: TestClient, file_id: int) -> str:
    response = client.get(
        f"/api/v1/files/{file_id}/chunks/1",
        params={"chunk_range": 25},
    )
    assert response.status_code == 200, response.text
    return "\n".join(chunk["content"] for chunk in response.json()["chunks"])


def _wire_worker(client: TestClient):
    """Make the test worker read the stored prompt snapshot per job."""
    worker = client.app.state.ingest_worker
    defaults = ingest_runtime_defaults(client.app.state.settings)
    worker.config_provider = lambda: load_ingest_runtime_config(
        client.app.state.db.session_factory,
        defaults,
    )
    return worker


def _clone_file(engine: Engine, source_id: int, *, current: bool) -> int:
    """Clone a file row as a newer version, optionally making it the current row."""
    with engine.begin() as connection:
        if current:
            connection.execute(
                text(
                    "UPDATE file SET is_current = false, updated_at = now() "
                    "WHERE id = :source_id"
                ),
                {"source_id": source_id},
            )
            connection.execute(
                text(
                    "UPDATE chunk SET is_current = false "
                    "WHERE source_kind = 'file' AND source_id = :source_id"
                ),
                {"source_id": source_id},
            )
        return int(
            connection.execute(
                text(
                    "INSERT INTO file ("
                    "user_id, raw_file_path, file_name, extension, mime_type, "
                    "size_bytes, content_hash, storage_key, storage_backend, "
                    "ai_summary, ai_tags, document_type, extraction_method, "
                    "vision_prompt_sha256, vision_prompt_mode, "
                    "vision_description_language, version, supersedes_file_id, "
                    "is_current, total_chunks, created_at, updated_at"
                    ") SELECT "
                    "user_id, raw_file_path, file_name, extension, mime_type, "
                    "size_bytes, content_hash, storage_key, storage_backend, "
                    "ai_summary, ai_tags, document_type, extraction_method, "
                    "vision_prompt_sha256, vision_prompt_mode, "
                    "vision_description_language, version + 1, id, "
                    ":is_current, 0, now(), now() "
                    "FROM file WHERE id = :source_id "
                    "RETURNING id"
                ),
                {"source_id": source_id, "is_current": current},
            ).scalar_one()
        )


def _mark_reingest_job_processing_stale(
    engine: Engine,
    job_id: int,
    staged_file_id: int,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file_ingest_job SET status = 'parsing', "
                "stage = 'Reading and extracting text', file_id = :staged_file_id, "
                "updated_at = now() - interval '1 hour' WHERE id = :job_id"
            ),
            {"job_id": job_id, "staged_file_id": staged_file_id},
        )


class FakeVisionExtractor:
    """Records prompts and can fail a configured number of extractions."""

    configured = True
    model_name = "fake-vision"

    def __init__(self, *, fail_times: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_times = fail_times

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        self.calls.append((system_prompt, mode))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise VisionExtractionError("synthetic provider failure")
        return VisionDocument(
            text="Receipt total 42",
            caption="A receipt",
            ocr_text="Receipt total 42",
            title="Receipt",
            summary="A receipt for 42.",
            document_type="receipt",
            tags=["receipt"],
            language="en",
            description=DESCRIPTION,
            tables=[TABLE],
        )


class _RaceVisionExtractor(FakeVisionExtractor):
    """Publishes a newer upload while the re-ingest extraction is running."""

    def __init__(self, engine: Engine, source_id: int) -> None:
        super().__init__()
        self.engine = engine
        self.source_id = source_id
        self.newer_file_id: int | None = None

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        vision = await super().extract(
            data,
            mime_type,
            system_prompt=system_prompt,
            mode=mode,
        )
        if self.newer_file_id is None:
            self.newer_file_id = _clone_file(self.engine, self.source_id, current=True)
        return vision


def test_reingest_creates_new_version_and_reuses_original(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A re-ingest publishes version 2 from the original bytes and new prompt."""
    document_prompt = _prompt("Document prompt")
    _save_prompts(client, _prompt("Image prompt v1"), document_prompt)

    fake = FakeVisionExtractor()
    client.app.state.vision_extractor = fake
    source = _upload_image(client, "/reingest/receipt.png")
    source_id = int(source["id"])
    assert source["version"] == 1
    assert source["is_current"] is True

    image_prompt = _prompt("Image prompt v2")
    _save_prompts(client, image_prompt, document_prompt)
    rendered = render_vision_prompt(image_prompt, "English", mode="image")
    worker = _wire_worker(client)

    enqueued = _enqueue(client, source_id, 1)
    assert enqueued.status_code == 202, enqueued.text
    job = enqueued.json()
    assert job["source_kind"] == "reingest"
    assert job["source_file_id"] == source_id
    assert job["file_id"] is None
    assert job["status"] == "queued"
    assert job["path"] == "/reingest/receipt.png"

    # The source remains the current, readable version until the job publishes.
    before = client.get(f"/api/v1/files/{source_id}")
    assert before.status_code == 200
    assert before.json()["is_current"] is True
    assert client.get(f"/api/v1/files/{source_id}/content").content == BLUE_PNG

    assert client.portal is not None
    processed = client.portal.call(worker.process_job, job["id"])
    assert processed is not None
    assert processed.status == "ready"

    state = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert state.status_code == 200, state.text
    state_body = state.json()
    new_id = int(state_body["file_id"])
    assert new_id != source_id
    assert state_body["source_file_id"] == source_id
    assert state_body["status"] == "ready"

    new_file = client.get(f"/api/v1/files/{new_id}")
    assert new_file.status_code == 200
    new_body = new_file.json()
    assert new_body["version"] == 2
    assert new_body["supersedes_file_id"] == source_id
    assert new_body["is_current"] is True
    assert new_body["has_original"] is True
    assert new_body["vision_prompt_sha256"] == rendered.sha256
    assert new_body["vision_prompt_mode"] == "image"
    assert new_body["vision_description_language"] == "English"
    assert client.get(f"/api/v1/files/{new_id}/content").content == BLUE_PNG
    assert fake.calls[-1] == (rendered.system_prompt, "image")

    old_file = client.get(f"/api/v1/files/{source_id}")
    assert old_file.status_code == 200
    old_body = old_file.json()
    assert old_body["version"] == 1
    assert old_body["is_current"] is False
    assert old_body["deleted_at"] is None
    assert client.get(f"/api/v1/files/{source_id}/content").content == BLUE_PNG

    old_chunks = client.get(
        f"/api/v1/files/{source_id}/chunks/1",
        params={"chunk_range": 25},
    )
    assert old_chunks.status_code == 200
    assert old_chunks.json()["chunks"]
    assert all(chunk["is_current"] is False for chunk in old_chunks.json()["chunks"])
    new_chunks = _chunk_text(client, new_id)
    assert "Receipt total 42" in new_chunks
    assert TABLE in new_chunks
    assert DESCRIPTION in new_chunks

    # The two versions share the exact same stored original object.
    with owner_engine.connect() as connection:
        storage_keys = dict(
            connection.execute(
                text("SELECT id, storage_key FROM file WHERE id IN (:old, :new)"),
                {"old": source_id, "new": new_id},
            ).all()
        )
    assert storage_keys[source_id] is not None
    assert storage_keys[source_id] == storage_keys[new_id]

    search = client.get(
        "/api/v1/search",
        params={"query": "Receipt total 42", "result_number": 5},
    )
    assert search.status_code == 200, search.text
    searched_ids = {item["file_id"] for item in search.json()["file_results"]}
    assert new_id in searched_ids
    assert source_id not in searched_ids


def test_reingest_failure_and_startup_recovery_preserve_source_bytes(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """Failure and crash recovery discard only staged output, never the original."""
    _save_prompts(client, _prompt("Image prompt"), _prompt("Document prompt"))
    client.app.state.vision_extractor = FakeVisionExtractor()
    source = _upload_image(client, "/reingest/failure.png")
    source_id = int(source["id"])
    worker = _wire_worker(client)
    worker.max_attempts = 1

    client.app.state.vision_extractor = FakeVisionExtractor(fail_times=1)
    enqueued = _enqueue(client, source_id, 1)
    assert enqueued.status_code == 202, enqueued.text
    job = enqueued.json()
    assert client.portal is not None
    processed = client.portal.call(worker.process_job, job["id"])
    assert processed is not None
    assert processed.status == "failed"
    assert processed.error_code == "vision_extraction_failed"
    assert processed.attempts == 1
    assert processed.file_id is None
    assert processed.source_file_id == source_id

    still_current = client.get(f"/api/v1/files/{source_id}")
    assert still_current.status_code == 200
    assert still_current.json()["is_current"] is True
    assert client.get(f"/api/v1/files/{source_id}/content").content == BLUE_PNG

    # Simulate a worker crash after it staged a new version for the same source.
    staged_id = _clone_file(owner_engine, source_id, current=False)
    _mark_reingest_job_processing_stale(owner_engine, int(job["id"]), staged_id)

    recovered = client.portal.call(worker.startup)
    assert recovered == 1

    recovered_job = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert recovered_job.status_code == 200
    recovered_body = recovered_job.json()
    assert recovered_body["status"] == "failed"
    assert recovered_body["error_code"] == "ingest_worker_lost"
    assert recovered_body["file_id"] is None
    assert recovered_body["source_file_id"] == source_id
    assert client.get(f"/api/v1/files/{staged_id}").status_code == 404

    after_recovery = client.get(f"/api/v1/files/{source_id}")
    assert after_recovery.status_code == 200
    assert after_recovery.json()["is_current"] is True
    assert client.get(f"/api/v1/files/{source_id}/content").content == BLUE_PNG


def test_reingest_rejects_invalid_sources(
    client: TestClient,
    user_client_factory,
    owner_engine: Engine,
) -> None:
    """Stale, missing, deleted, text, other-account, and unconfigured sources fail."""
    client.app.state.vision_extractor = FakeVisionExtractor()
    source = _upload_image(client, "/reingest/valid.png")
    source_id = int(source["id"])

    stale = _enqueue(client, source_id, 2)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"] == "file_version_conflict"

    text_file = create_text(
        client,
        "/reingest/plain.txt",
        "Plain text is not a vision source. " * 40,
    )
    text_response = _enqueue(client, int(text_file["id"]), 1)
    assert text_response.status_code == 422, text_response.text
    assert text_response.json()["error"] == "unsupported_file_type"

    deleted_file = _upload_image(client, "/reingest/deleted.png")
    deleted_id = int(deleted_file["id"])
    assert client.delete(f"/api/v1/files/{deleted_id}").status_code == 204
    deleted_response = _enqueue(client, deleted_id, 1)
    assert deleted_response.status_code == 404, deleted_response.text
    assert deleted_response.json()["error"] == "file_not_found"

    historical = _upload_image(client, "/reingest/duplicate.png")
    _upload_image(client, "/reingest/duplicate.png")
    historical_response = _enqueue(client, int(historical["id"]), 1)
    assert historical_response.status_code == 404, historical_response.text
    assert historical_response.json()["error"] == "file_not_found"

    without_original = _upload_image(client, "/reingest/no-original.png")
    without_original_id = int(without_original["id"])
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE file SET storage_key = NULL, storage_backend = NULL "
                "WHERE id = :file_id"
            ),
            {"file_id": without_original_id},
        )
    no_original = _enqueue(client, without_original_id, 1)
    assert no_original.status_code == 404, no_original.text
    assert no_original.json()["error"] == "file_content_unavailable"

    member = user_client_factory()
    other_account = member.client.post(
        f"/api/v1/files/{source_id}/reingest",
        json={"expected_version": 1},
    )
    assert other_account.status_code == 404, other_account.text
    assert other_account.json()["error"] == "file_not_found"

    client.app.state.vision_extractor = NullVisionExtractor()
    unconfigured = _enqueue(client, source_id, 1)
    assert unconfigured.status_code == 503, unconfigured.text
    assert unconfigured.json()["error"] == "ai_not_configured"

    jobs = client.get("/api/v1/files/ingest-jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total_results"] == 0


def test_reingest_publish_race_conflict_and_retry(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    """A newer upload wins the race; duplicates conflict and retry keeps the source."""
    document_prompt = _prompt("Document prompt")
    _save_prompts(client, _prompt("Image prompt v1"), document_prompt)
    client.app.state.vision_extractor = FakeVisionExtractor()
    source = _upload_image(client, "/reingest/retry.png")
    source_id = int(source["id"])
    worker = _wire_worker(client)

    enqueued = _enqueue(client, source_id, 1)
    assert enqueued.status_code == 202, enqueued.text
    job = enqueued.json()

    duplicate = _enqueue(client, source_id, 1)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"] == "ingest_job_conflict"

    # Fail the first attempt, then retry after saving a new prompt.
    client.app.state.vision_extractor = FakeVisionExtractor(fail_times=1)
    assert client.portal is not None
    failed = client.portal.call(worker.process_job, job["id"])
    assert failed is not None
    assert failed.status == "failed"
    assert failed.source_file_id == source_id

    image_prompt = _prompt("Image prompt retry")
    _save_prompts(client, image_prompt, document_prompt)
    rendered = render_vision_prompt(image_prompt, "English", mode="image")

    retried = client.post(f"/api/v1/files/ingest-jobs/{job['id']}/retry")
    assert retried.status_code == 202, retried.text
    retried_body = retried.json()
    assert retried_body["status"] == "queued"
    assert retried_body["source_kind"] == "reingest"
    assert retried_body["source_file_id"] == source_id
    assert retried_body["attempts"] == 1

    retried_process = client.portal.call(worker.process_job, job["id"])
    assert retried_process is not None
    assert retried_process.status == "ready"
    assert retried_process.source_file_id == source_id
    retried_file = client.get(f"/api/v1/files/{int(retried_process.file_id)}")
    assert retried_file.status_code == 200
    assert retried_file.json()["version"] == 2
    assert retried_file.json()["vision_prompt_sha256"] == rendered.sha256
    assert retried_file.json()["vision_prompt_mode"] == "image"

    # A newer upload published during extraction must stay current.
    client.app.state.vision_extractor = FakeVisionExtractor()
    race_source = _upload_image(client, "/reingest/race.png")
    race_source_id = int(race_source["id"])
    race_enqueued = _enqueue(client, race_source_id, 1)
    assert race_enqueued.status_code == 202, race_enqueued.text
    race_job = race_enqueued.json()

    race = _RaceVisionExtractor(owner_engine, race_source_id)
    client.app.state.vision_extractor = race
    raced = client.portal.call(worker.process_job, race_job["id"])
    assert raced is not None
    assert raced.status == "failed"
    assert raced.error_code == "ingest_source_stale"
    assert raced.source_file_id == race_source_id
    assert race.newer_file_id is not None
    newer_id = race.newer_file_id
    assert newer_id != race_source_id

    newer = client.get(f"/api/v1/files/{newer_id}")
    assert newer.status_code == 200
    assert newer.json()["is_current"] is True
    assert newer.json()["version"] == 2
    assert client.get(f"/api/v1/files/{newer_id}/content").content == BLUE_PNG

    old_race_source = client.get(f"/api/v1/files/{race_source_id}")
    assert old_race_source.status_code == 200
    assert old_race_source.json()["is_current"] is False
    assert client.get(f"/api/v1/files/{race_source_id}/content").content == BLUE_PNG

    race_state = client.get(f"/api/v1/files/ingest-jobs/{race_job['id']}")
    assert race_state.status_code == 200
    assert race_state.json()["status"] == "failed"
    assert race_state.json()["error_code"] == "ingest_source_stale"
    assert race_state.json()["file_id"] is None
