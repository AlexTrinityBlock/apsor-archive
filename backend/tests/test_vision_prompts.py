"""Editable vision prompts: validation, rendering, and extraction fingerprints."""

import base64
import hashlib
from io import BytesIO
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.module.knowledge.dependencies import (
    ingest_runtime_defaults,
    load_ingest_runtime_config,
)
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    DEFAULT_VISION_IMAGE_PROMPT,
    VISION_LANGUAGE_PLACEHOLDER,
    VISION_PROMPT_MAX_CHARS,
    VISION_REQUIRED_JSON_KEYS,
    normalize_vision_prompt,
    prompt_warnings,
    render_vision_prompt,
    validate_vision_prompt,
    vision_mode_for_extension,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

# A 1x1 blue PNG; enough to exercise the image extension and vision path.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

DESCRIPTION = "A white receipt on a blue table with a red square."
TABLE = "| Item | Price |\n|---|---|\n| Widget | 42 |"


def _prompt(label: str, *, include_safety: bool = True) -> str:
    """Build a valid template that mentions every required output key."""
    text = (
        f"{label}. Return one JSON object with the keys text, tables, description, "
        f"caption, title, summary, document_type, tags, and language. "
        f"Use {VISION_LANGUAGE_PLACEHOLDER} for description, caption, title, summary, "
        "and tags. Copy OCR text and cell text exactly as seen."
    )
    if include_safety:
        text += (
            " Keep OCR text verbatim. Do not translate. "
            "Use GitHub-Flavored Markdown tables."
        )
    return text


def _save_prompts(
    client: TestClient,
    image_prompt: str,
    document_prompt: str,
) -> dict[str, object]:
    """Save both prompt templates through the root-only settings route."""
    response = client.put(
        "/api/v1/settings/ingest/vision-prompts",
        json={"image_prompt": image_prompt, "document_prompt": document_prompt},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _chunk_text(client: TestClient, file_id: int) -> str:
    """Read every chunk of one file through the public API."""
    response = client.get(
        f"/api/v1/files/{file_id}/chunks/1",
        params={"chunk_range": 25},
    )
    assert response.status_code == 200, response.text
    return "\n".join(chunk["content"] for chunk in response.json()["chunks"])


def _blank_pdf() -> bytes:
    """Build one valid page with no extractable text, like a scanned page."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _wire_worker(client: TestClient):
    """Make the test worker read the stored prompt snapshot per job."""
    worker = client.app.state.ingest_worker
    defaults = ingest_runtime_defaults(client.app.state.settings)
    worker.config_provider = lambda: load_ingest_runtime_config(
        client.app.state.db.session_factory,
        defaults,
    )
    return worker


class FakeVisionExtractor:
    """Records the exact system prompt and mode, then returns one vision document."""

    configured = True
    model_name = "fake-vision"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        self.calls.append((system_prompt, mode))
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


def test_vision_prompt_settings_roundtrip_and_validation(client: TestClient) -> None:
    """Defaults, custom save, runtime reset, warnings, and save-time rejection."""
    initial = client.get("/api/v1/settings/ingest/vision-prompts")
    assert initial.status_code == 200, initial.text
    initial_body = initial.json()
    expected_defaults = {
        "image_prompt": DEFAULT_VISION_IMAGE_PROMPT,
        "document_prompt": DEFAULT_VISION_DOCUMENT_PROMPT,
    }
    assert initial_body["source"] == "default"
    assert initial_body["config"] == expected_defaults
    assert initial_body["defaults"] == expected_defaults
    assert initial_body["max_chars"] == VISION_PROMPT_MAX_CHARS
    assert tuple(initial_body["required_keys"]) == VISION_REQUIRED_JSON_KEYS
    assert initial_body["warnings"] == []
    assert initial_body["image_prompt_sha256"] == hashlib.sha256(
        DEFAULT_VISION_IMAGE_PROMPT.encode("utf-8")
    ).hexdigest()
    assert initial_body["document_prompt_sha256"] == hashlib.sha256(
        DEFAULT_VISION_DOCUMENT_PROMPT.encode("utf-8")
    ).hexdigest()

    # Safety warnings are advisory: saving still succeeds.
    warning_save = _save_prompts(
        client,
        _prompt("Warning image", include_safety=False),
        _prompt("Warning document", include_safety=False),
    )
    assert warning_save["source"] == "database"
    assert set(warning_save["warnings"]) == {
        "missing_verbatim",
        "missing_translation_rule",
        "missing_table_rule",
    }

    image_prompt = _prompt("Custom image")
    document_prompt = _prompt("Custom document")
    saved = _save_prompts(client, image_prompt, document_prompt)
    assert saved["source"] == "database"
    assert saved["config"] == {
        "image_prompt": image_prompt,
        "document_prompt": document_prompt,
    }
    assert saved["warnings"] == []
    assert saved["image_prompt_sha256"] == hashlib.sha256(
        image_prompt.encode("utf-8")
    ).hexdigest()
    assert saved["document_prompt_sha256"] == hashlib.sha256(
        document_prompt.encode("utf-8")
    ).hexdigest()

    persisted = client.get("/api/v1/settings/ingest/vision-prompts")
    assert persisted.status_code == 200
    assert persisted.json()["config"] == saved["config"]

    # A runtime reset restores worker knobs but never wipes custom prompts.
    reset = client.post("/api/v1/settings/ingest/reset")
    assert reset.status_code == 200, reset.text
    after_reset = client.get("/api/v1/settings/ingest/vision-prompts")
    assert after_reset.status_code == 200
    assert after_reset.json()["config"] == saved["config"]
    assert after_reset.json()["source"] == "database"

    invalid_cases = (
        (
            {"image_prompt": image_prompt.replace("summary", "")},
            "summary",
        ),
        (
            {"image_prompt": "x" * (VISION_PROMPT_MAX_CHARS + 1)},
            "32000",
        ),
        (
            {"image_prompt": image_prompt + "\x00"},
            "control",
        ),
    )
    for overrides, expected_detail in invalid_cases:
        payload = {
            "image_prompt": image_prompt,
            "document_prompt": document_prompt,
            **overrides,
        }
        rejected = client.put(
            "/api/v1/settings/ingest/vision-prompts",
            json=payload,
        )
        assert rejected.status_code == 422, rejected.text
        body = rejected.json()
        assert body["error"] == "invalid_vision_prompt"
        assert expected_detail in body["detail"]

    unchanged = client.get("/api/v1/settings/ingest/vision-prompts")
    assert unchanged.status_code == 200
    assert unchanged.json()["config"] == saved["config"]


def test_vision_prompt_rendering_and_hash() -> None:
    """The placeholder is JSON-quoted and the fingerprint covers the exact prompt."""
    template = f"Describe the image in {VISION_LANGUAGE_PLACEHOLDER} and return text."
    rendered = render_vision_prompt(template, "Traditional Chinese")

    assert rendered.system_prompt == 'Describe the image in "Traditional Chinese" and return text.'
    assert VISION_LANGUAGE_PLACEHOLDER not in rendered.system_prompt
    assert rendered.sha256 == hashlib.sha256(
        rendered.system_prompt.encode("utf-8")
    ).hexdigest()
    assert rendered.mode == "image"
    assert rendered.description_language == "Traditional Chinese"

    # Without the placeholder the template is used verbatim, but the mode and
    # fingerprint still describe the exact prompt that is sent.
    fixed = render_vision_prompt(
        "A fixed prompt with no placeholder.",
        "Japanese",
        mode="document",
    )
    assert fixed.system_prompt == "A fixed prompt with no placeholder."
    assert fixed.mode == "document"
    assert fixed.description_language == "Japanese"
    assert fixed.sha256 == hashlib.sha256(
        fixed.system_prompt.encode("utf-8")
    ).hexdigest()

    assert vision_mode_for_extension("/archive/scan.pdf") == "document"
    assert vision_mode_for_extension("/archive/photo.png") == "image"
    assert vision_mode_for_extension("/archive/report.docx") == "image"
    assert vision_mode_for_extension("/archive/notes.txt") is None

    assert normalize_vision_prompt("  padded prompt  ") == "padded prompt"
    with pytest.raises(ValueError, match="summary"):
        validate_vision_prompt(_prompt("Missing summary").replace("summary", ""))
    assert prompt_warnings(_prompt("Safe prompt")) == ()
    assert set(prompt_warnings("A prompt with no safety rules.")) == {
        "missing_verbatim",
        "missing_translation_rule",
        "missing_table_rule",
    }


def test_sync_image_uses_custom_image_prompt_and_prompt_save_keeps_existing_file(
    client: TestClient,
) -> None:
    """A sync upload sends the saved image prompt and records its fingerprint."""
    image_prompt = _prompt("Image prompt v1")
    document_prompt = _prompt("Document prompt v1")
    _save_prompts(client, image_prompt, document_prompt)

    fake = FakeVisionExtractor()
    client.app.state.vision_extractor = fake
    rendered = render_vision_prompt(image_prompt, "English", mode="image")

    uploaded = client.post(
        "/api/v1/files",
        data={"path": "/vision/custom-image.png"},
        files={"file": ("custom-image.png", BLUE_PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    file = uploaded.json()
    assert fake.calls == [(rendered.system_prompt, "image")]
    assert file["extraction_method"] == "vision"
    assert file["vision_prompt_sha256"] == rendered.sha256
    assert file["vision_prompt_mode"] == "image"
    assert file["vision_description_language"] == "English"

    chunks_before = _chunk_text(client, int(file["id"]))
    assert "Receipt total 42" in chunks_before
    assert TABLE in chunks_before
    assert DESCRIPTION in chunks_before

    # Saving a new prompt must not rewrite existing extraction or queue a job.
    _save_prompts(client, _prompt("Image prompt v2"), document_prompt)
    after = client.get(f"/api/v1/files/{file['id']}")
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["vision_prompt_sha256"] == rendered.sha256
    assert after_body["vision_prompt_mode"] == "image"
    assert after_body["vision_description_language"] == "English"
    assert _chunk_text(client, int(file["id"])) == chunks_before

    jobs = client.get("/api/v1/files/ingest-jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total_results"] == 0


def test_worker_scanned_pdf_uses_custom_document_prompt(client: TestClient) -> None:
    """A scanned PDF reuses the document prompt and records document mode."""
    image_prompt = _prompt("Image prompt")
    document_prompt = _prompt("Document prompt")
    _save_prompts(client, image_prompt, document_prompt)

    fake = FakeVisionExtractor()
    client.app.state.vision_extractor = fake
    worker = _wire_worker(client)
    rendered = render_vision_prompt(document_prompt, "English", mode="document")

    queued = client.post(
        "/api/v1/files/async",
        data={"path": "/vision/scanned-page.pdf"},
        files={"file": ("scanned-page.pdf", _blank_pdf(), "application/pdf")},
    )
    assert queued.status_code == 202, queued.text
    job = queued.json()
    assert job["status"] == "queued"
    assert client.portal is not None

    processed = client.portal.call(worker.process_job, job["id"])
    assert processed is not None
    assert processed.status == "ready"
    assert fake.calls == [(rendered.system_prompt, "document")]

    state = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert state.status_code == 200, state.text
    state_body = state.json()
    assert state_body["status"] == "ready"
    file_id = int(state_body["file_id"])

    file = client.get(f"/api/v1/files/{file_id}")
    assert file.status_code == 200
    file_body = file.json()
    assert file_body["extraction_method"] == "vision"
    assert file_body["vision_prompt_mode"] == "document"
    assert file_body["vision_prompt_sha256"] == rendered.sha256
    assert file_body["vision_description_language"] == "English"
    assert "Receipt total 42" in _chunk_text(client, file_id)
