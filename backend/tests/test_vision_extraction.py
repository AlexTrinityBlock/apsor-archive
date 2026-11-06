"""Vision prompt contracts and language-aware image extraction."""

import asyncio
import base64
from typing import Any, Literal

from fastapi.testclient import TestClient

from app.infrastructure.ai.vision_extractor import (
    VISION_DOCUMENT_MAX_TOKENS,
    VISION_IMAGE_MAX_TOKENS,
    DeepSeekVisionExtractor,
    build_vision_prompt,
)
from app.module.knowledge.dependencies import (
    ingest_runtime_defaults,
    load_ingest_runtime_config,
)
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_IMAGE_PROMPT,
    render_vision_prompt,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

# A 1x1 blue PNG; enough to exercise the image extension and vision path.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

DESCRIPTION = "A white receipt on a blue table with a red square."
TABLE = "| Item | Price |\n|---|---|\n| Widget | 42 |"


class _StubVisionClient:
    """Deterministic stand-in for the provider HTTP call."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def analyze(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "data": data,
                "mime_type": mime_type,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
            }
        )
        return self.response


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


def _chunk_text(client: TestClient, file_id: int) -> str:
    """Read every chunk of one file through the public API."""
    response = client.get(
        f"/api/v1/files/{file_id}/chunks/1",
        params={"chunk_range": 25},
    )
    assert response.status_code == 200, response.text
    return "\n".join(chunk["content"] for chunk in response.json()["chunks"])


def test_vision_prompt_contract_and_parsing() -> None:
    image_prompt = build_vision_prompt("Traditional Chinese", "image")
    document_prompt = build_vision_prompt("Traditional Chinese", "document")

    assert '"Traditional Chinese"' in image_prompt
    assert "verbatim" in image_prompt
    assert "original language" in image_prompt
    assert "GitHub-Flavored Markdown" in image_prompt
    assert "Do not translate" in image_prompt
    assert "complete visual description" in image_prompt
    assert "brief layout note" not in image_prompt

    assert '"Traditional Chinese"' in document_prompt
    assert "verbatim" in document_prompt
    assert "GitHub-Flavored Markdown" in document_prompt
    assert "Do not translate" in document_prompt
    assert "brief layout note" in document_prompt
    normalized_document_prompt = " ".join(document_prompt.split())
    assert "Do not produce an exhaustive visual essay" in normalized_document_prompt
    assert "preserves line breaks" in normalized_document_prompt
    assert "complete visual description" not in document_prompt

    extractor = DeepSeekVisionExtractor(
        api_key="test-key",
        base_url="http://vision.invalid",
        model="vision-test",
        timeout_seconds=0.01,
    )
    stub = _StubVisionClient(
        {
            "text": " Grand total 42 ",
            "tables": [f" {TABLE} "],
            "description": f" {DESCRIPTION} ",
            "caption": "A receipt",
            "title": "Receipt",
            "summary": "A receipt for 42.",
            "document_type": "Receipt",
            "tags": ["receipt", "total"],
            "language": "en",
        }
    )
    extractor._client = stub  # type: ignore[assignment]

    parsed = asyncio.run(
        extractor.extract(
            BLUE_PNG,
            "image/png",
            system_prompt=image_prompt,
            mode="image",
        )
    )
    assert stub.calls[0]["system_prompt"] == image_prompt
    assert stub.calls[0]["max_tokens"] == VISION_IMAGE_MAX_TOKENS
    assert "this image" in stub.calls[0]["user_prompt"]
    assert parsed.text == "Grand total 42"
    assert parsed.ocr_text == "Grand total 42"
    assert parsed.description == DESCRIPTION
    assert parsed.tables == [TABLE]
    assert parsed.document_type == "receipt"
    assert parsed.title == "Receipt"
    assert parsed.tags == ["receipt", "total"]

    # Missing optional fields default cleanly; a lone table string is wrapped.
    stub.response = {"text": " only text ", "tables": f" {TABLE} "}
    missing = asyncio.run(
        extractor.extract(
            BLUE_PNG,
            "image/png",
            system_prompt=document_prompt,
            mode="document",
        )
    )
    assert stub.calls[1]["system_prompt"] == document_prompt
    assert stub.calls[1]["max_tokens"] == VISION_DOCUMENT_MAX_TOKENS
    assert "document page" in stub.calls[1]["user_prompt"]
    assert missing.text == "only text"
    assert missing.ocr_text == "only text"
    assert missing.tables == [TABLE]
    assert missing.description == ""
    assert missing.caption == ""
    assert missing.summary == ""
    assert missing.document_type == "other"
    assert missing.title == "Untitled document"
    assert missing.tags == []
    assert missing.language == ""


def test_vision_description_language_applies_to_sync_and_async_ingest(
    client: TestClient,
) -> None:
    initial = client.get("/api/v1/settings/ingest")
    assert initial.status_code == 200, initial.text
    initial_body = initial.json()
    assert initial_body["source"] == "default"
    assert initial_body["defaults"]["vision_description_language"] == "English"
    assert initial_body["config"]["vision_description_language"] == "English"

    traditional_chinese = {
        **initial_body["config"],
        "vision_description_language": "Traditional Chinese",
    }
    stored = client.put("/api/v1/settings/ingest", json=traditional_chinese)
    assert stored.status_code == 200, stored.text
    assert stored.json()["source"] == "database"
    assert stored.json()["config"] == traditional_chinese

    persisted = client.get("/api/v1/settings/ingest")
    assert persisted.status_code == 200
    assert persisted.json()["source"] == "database"
    assert persisted.json()["config"] == traditional_chinese

    fake = FakeVisionExtractor()
    client.app.state.vision_extractor = fake
    traditional_rendered = render_vision_prompt(
        DEFAULT_VISION_IMAGE_PROMPT,
        "Traditional Chinese",
        mode="image",
    )

    sync_upload = client.post(
        "/api/v1/files",
        data={"path": "/vision/sync-receipt.png"},
        files={"file": ("sync-receipt.png", BLUE_PNG, "image/png")},
    )
    assert sync_upload.status_code == 201, sync_upload.text
    sync_file = sync_upload.json()
    assert sync_file["extraction_method"] == "vision"
    assert sync_file["vision_prompt_sha256"] == traditional_rendered.sha256
    assert sync_file["vision_prompt_mode"] == "image"
    assert sync_file["vision_description_language"] == "Traditional Chinese"
    assert fake.calls == [(traditional_rendered.system_prompt, "image")]

    sync_chunks = _chunk_text(client, int(sync_file["id"]))
    assert "## Visible text" in sync_chunks
    assert "Receipt total 42" in sync_chunks
    assert "## Tables" in sync_chunks
    assert TABLE in sync_chunks
    assert "## Visual description" in sync_chunks
    assert DESCRIPTION in sync_chunks

    worker = client.app.state.ingest_worker
    defaults = ingest_runtime_defaults(client.app.state.settings)
    worker.config_provider = lambda: load_ingest_runtime_config(
        client.app.state.db.session_factory,
        defaults,
    )
    queued = client.post(
        "/api/v1/files/async",
        data={"path": "/vision/async-receipt.png"},
        files={"file": ("async-receipt.png", BLUE_PNG, "image/png")},
    )
    assert queued.status_code == 202, queued.text
    job = queued.json()
    assert job["status"] == "queued"
    assert client.portal is not None

    processed = client.portal.call(worker.process_job, job["id"])
    assert processed is not None
    assert processed.status == "ready"
    assert fake.calls[-1] == (traditional_rendered.system_prompt, "image")

    async_state = client.get(f"/api/v1/files/ingest-jobs/{job['id']}")
    assert async_state.status_code == 200, async_state.text
    async_file_id = int(async_state.json()["file_id"])
    async_file = client.get(f"/api/v1/files/{async_file_id}").json()
    assert async_file["vision_prompt_sha256"] == traditional_rendered.sha256
    assert async_file["vision_prompt_mode"] == "image"
    assert async_file["vision_description_language"] == "Traditional Chinese"
    async_chunks = _chunk_text(client, async_file_id)
    assert "Receipt total 42" in async_chunks
    assert TABLE in async_chunks
    assert DESCRIPTION in async_chunks

    # A later language change affects only new ingests; stored chunks stay put.
    japanese = {
        **traditional_chinese,
        "vision_description_language": "Japanese",
    }
    changed = client.put("/api/v1/settings/ingest", json=japanese)
    assert changed.status_code == 200, changed.text
    assert changed.json()["config"]["vision_description_language"] == "Japanese"

    japanese_upload = client.post(
        "/api/v1/files",
        data={"path": "/vision/japanese-receipt.png"},
        files={"file": ("japanese-receipt.png", BLUE_PNG, "image/png")},
    )
    assert japanese_upload.status_code == 201, japanese_upload.text
    japanese_rendered = render_vision_prompt(
        DEFAULT_VISION_IMAGE_PROMPT,
        "Japanese",
        mode="image",
    )
    assert fake.calls[-1] == (japanese_rendered.system_prompt, "image")
    assert japanese_upload.json()["vision_prompt_sha256"] == japanese_rendered.sha256
    assert japanese_upload.json()["vision_description_language"] == "Japanese"
    assert _chunk_text(client, int(sync_file["id"])) == sync_chunks
    assert _chunk_text(client, async_file_id) == async_chunks

    reset = client.post("/api/v1/settings/ingest/reset")
    assert reset.status_code == 200, reset.text
    reset_body = reset.json()
    assert reset_body["source"] == "database"
    assert reset_body["config"]["vision_description_language"] == "English"
    assert reset_body["defaults"]["vision_description_language"] == "English"

    prompts = client.get("/api/v1/settings/ingest/vision-prompts")
    assert prompts.status_code == 200, prompts.text
    assert prompts.json()["source"] == "default"
    assert prompts.json()["config"]["image_prompt"] == DEFAULT_VISION_IMAGE_PROMPT
