"""WebP file thumbnails: rendering, reuse, caching, isolation, and backfill."""

import io
import zipfile
import zlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from sqlalchemy import Engine, text

from app.module.agent.service.tool_registry import AgentToolRegistry
from app.module.knowledge.dependencies import build_thumbnail_backfill
from app.module.knowledge.domain.thumbnail_domain import (
    THUMBNAIL_MAX_EDGE,
    RenderedThumbnail,
    ThumbnailRenderError,
    thumbnail_version,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument
from app.module.knowledge.schema.file_schema import FileSchema
from app.module.knowledge.service.thumbnail_renderer import render_thumbnail
from tests.conftest import UserClient, rls_connection
from tests.helpers import build_pptx_deck


class _FakeVisionExtractor:
    """Offline vision stand-in so image and scanned-PDF uploads index text."""

    configured = True
    model_name = "fake-vision"

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        del data, mime_type, system_prompt, mode
        return VisionDocument(
            text="A landscape photo of hills.",
            caption="Hills",
            ocr_text="",
            title="Hills",
            summary="A landscape photo.",
            document_type="photo",
            tags=["photo"],
            language="en",
            description="Rolling hills under a clear sky.",
            tables=[],
        )


class _CountingRenderer:
    """Wraps the real renderer and counts how often it actually runs."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, data: bytes, extension: str) -> RenderedThumbnail | None:
        self.calls += 1
        return render_thumbnail(data, extension)


def _png(width: int, height: int) -> bytes:
    image = Image.linear_gradient("L").resize((width, height)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _blank_pdf(width: float = 612, height: float = 792) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _office_package(deck: bytes, *, preview: bool, blank: bool = False) -> bytes:
    """Rewrite a package without its preview parts, optionally adding one."""
    source = zipfile.ZipFile(io.BytesIO(deck))
    target_buffer = io.BytesIO()
    with zipfile.ZipFile(target_buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename.startswith("docProps/thumbnail"):
                continue
            target.writestr(item, source.read(item.filename))
        if preview:
            image = io.BytesIO()
            picture = Image.new("RGB", (256, 192), (255, 255, 255) if blank else (40, 90, 160))
            if not blank:
                ImageDraw.Draw(picture).rectangle((24, 24, 160, 120), fill=(240, 200, 60))
            picture.save(image, format="JPEG")
            target.writestr("docProps/thumbnail.jpeg", image.getvalue())
    return target_buffer.getvalue()


def _upload(
    client: TestClient,
    path: str,
    data: bytes,
    mime_type: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/files",
        data={"path": path},
        files={"file": (path.rsplit("/", 1)[-1], data, mime_type)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _thumbnail_rows(owner_engine: Engine) -> dict[int, dict[str, Any]]:
    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT file_id, status, error_code, attempts, generator_version "
                "FROM file_thumbnail"
            )
        ).mappings()
        return {int(row["file_id"]): dict(row) for row in rows}


@pytest.fixture
def vision(client: TestClient) -> None:
    client.app.state.vision_extractor = _FakeVisionExtractor()


@pytest.mark.usefixtures("vision")
def test_async_image_upload_renders_a_cacheable_webp(client: TestClient) -> None:
    response = client.post(
        "/api/v1/files/async",
        data={"path": "/photos/hills.png"},
        files={"file": ("hills.png", _png(2000, 1000), "image/png")},
    )
    assert response.status_code == 202, response.text
    assert client.portal.call(client.app.state.ingest_worker.run_once) is True
    job = client.get(f"/api/v1/files/ingest-jobs/{response.json()['id']}").json()
    assert job["status"] == "ready", job
    file_id = int(job["file_id"])

    file = client.get(f"/api/v1/files/{file_id}").json()
    thumbnail = file["thumbnail"]
    assert thumbnail["width"] == THUMBNAIL_MAX_EDGE
    assert thumbnail["height"] == THUMBNAIL_MAX_EDGE // 2
    assert len(thumbnail["version"]) == 16

    listing = client.get("/api/v1/paths", params={"path": "/photos"})
    assert listing.status_code == 200, listing.text
    [listed] = listing.json()["files"]
    assert listed["thumbnail"] == thumbnail

    image = client.get(
        f"/api/v1/files/{file_id}/thumbnail",
        params={"v": thumbnail["version"]},
    )
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert image.headers["vary"] == "Cookie"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert len(image.content) <= 12 * 1024
    decoded = Image.open(io.BytesIO(image.content))
    assert decoded.format == "WEBP"
    assert decoded.size == (thumbnail["width"], thumbnail["height"])

    unversioned = client.get(f"/api/v1/files/{file_id}/thumbnail")
    assert unversioned.headers["cache-control"] == "private, max-age=0, must-revalidate"
    etag = unversioned.headers["etag"]
    assert etag.startswith('"') and not etag.startswith("W/")

    cached = client.get(
        f"/api/v1/files/{file_id}/thumbnail",
        headers={"If-None-Match": etag},
    )
    assert cached.status_code == 304
    assert cached.content == b""


@pytest.mark.usefixtures("vision")
def test_pdf_thumbnail_keeps_the_page_aspect(client: TestClient) -> None:
    file = _upload(client, "/docs/letter.pdf", _blank_pdf(), "application/pdf")
    thumbnail = file["thumbnail"]
    assert thumbnail is not None
    assert thumbnail["height"] == THUMBNAIL_MAX_EDGE
    assert thumbnail["width"] == round(THUMBNAIL_MAX_EDGE * 612 / 792)


def test_office_files_use_their_embedded_preview(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    with_preview = _upload(
        client,
        "/slides/with-preview.pptx",
        _office_package(build_pptx_deck(), preview=True),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert with_preview["thumbnail"] == {
        "version": with_preview["thumbnail"]["version"],
        "width": 256,
        "height": 192,
    }

    without_preview = _upload(
        client,
        "/slides/plain.pptx",
        _office_package(build_pptx_deck(), preview=False),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert without_preview["thumbnail"] is None
    rows = _thumbnail_rows(owner_engine)
    assert rows[int(without_preview["id"])]["status"] == "none"


def test_blank_embedded_office_preview_falls_back_to_the_client(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    # python-docx/python-pptx templates and some exporters embed a plain white
    # placeholder; a blank card is worse than letting the browser render page 1.
    blank = _upload(
        client,
        "/slides/blank-preview.pptx",
        _office_package(build_pptx_deck(), preview=True, blank=True),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    assert blank["thumbnail"] is None
    assert _thumbnail_rows(owner_engine)[int(blank["id"])]["status"] == "none"


def test_text_files_have_no_thumbnail(client: TestClient, owner_engine: Engine) -> None:
    file = _upload(client, "/notes/plain.txt", b"Plain text notes.", "text/plain")
    assert file["thumbnail"] is None
    assert int(file["id"]) not in _thumbnail_rows(owner_engine)

    missing = client.get(f"/api/v1/files/{file['id']}/thumbnail")
    assert missing.status_code == 404
    assert missing.json()["error"] == "thumbnail_not_found"

    unknown = client.get("/api/v1/files/999999/thumbnail")
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "file_not_found"


@pytest.mark.usefixtures("vision")
def test_render_failure_never_fails_the_ingest(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    def broken(data: bytes, extension: str) -> RenderedThumbnail | None:
        del data, extension
        raise ThumbnailRenderError("image_unreadable")

    client.app.state.thumbnail_renderer = broken
    file = _upload(client, "/photos/broken.png", _png(64, 64), "image/png")
    assert file["thumbnail"] is None
    row = _thumbnail_rows(owner_engine)[int(file["id"])]
    assert row["status"] == "failed"
    assert row["error_code"] == "image_unreadable"


@pytest.mark.usefixtures("vision")
def test_copy_move_and_folder_copy_reuse_the_thumbnail(client: TestClient) -> None:
    renderer = _CountingRenderer()
    client.app.state.thumbnail_renderer = renderer
    original = _upload(client, "/album/a/hills.png", _png(800, 600), "image/png")
    assert renderer.calls == 1
    version = original["thumbnail"]["version"]

    copied = client.post(
        f"/api/v1/files/{original['id']}/copy",
        json={"path": "/album/b/hills.png"},
    )
    assert copied.status_code in (200, 201), copied.text
    assert copied.json()["thumbnail"]["version"] == version

    moved = client.post(
        f"/api/v1/files/{original['id']}/move",
        json={"path": "/album/c/hills.png"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["thumbnail"]["version"] == version

    folder = client.post(
        "/api/v1/folders/copy",
        json={"path": "/album/c", "target_path": "/album/d"},
    )
    assert folder.status_code == 201, folder.text
    listing = client.get("/api/v1/paths", params={"path": "/album/d"}).json()
    [copied_in_folder] = listing["files"]
    assert copied_in_folder["thumbnail"]["version"] == version

    reuploaded = _upload(client, "/album/e/hills.png", _png(800, 600), "image/png")
    assert reuploaded["thumbnail"]["version"] == version
    assert renderer.calls == 1


def _png_claiming(width: int, height: int) -> bytes:
    """A real 1x1 PNG whose IHDR header claims a different canvas size."""
    data = bytearray(_png(1, 1))
    # Signature (8) + chunk length (4) + "IHDR" (4), then width and height.
    data[16:24] = width.to_bytes(4, "big") + height.to_bytes(4, "big")
    data[29:33] = zlib.crc32(bytes(data[12:29])).to_bytes(4, "big")
    return bytes(data)


@pytest.mark.parametrize("edge", [7_000, 30_000])
def test_oversized_images_fail_before_decoding(edge: int) -> None:
    # Pixel bombs must fail cleanly without Pillow's DecompressionBombWarning,
    # which the suite treats as an error.
    with pytest.raises(ThumbnailRenderError) as raised:
        render_thumbnail(_png_claiming(edge, edge), ".png")
    assert raised.value.code == "image_too_large"


@pytest.mark.usefixtures("vision")
def test_backfill_restores_missing_thumbnails_for_every_account(
    client: TestClient,
    owner_engine: Engine,
    user_client_factory: Callable[..., UserClient],
) -> None:
    member = user_client_factory()
    member.client.app.state.vision_extractor = _FakeVisionExtractor()
    mine = _upload(client, "/photos/mine.png", _png(400, 300), "image/png")
    theirs = _upload(member.client, "/photos/theirs.png", _png(300, 400), "image/png")
    notes = _upload(client, "/notes/skip.txt", b"Not visual.", "text/plain")
    with owner_engine.begin() as connection:
        connection.execute(text("DELETE FROM file_thumbnail"))

    backfill = build_thumbnail_backfill(client.app.state, client.app.state.db)
    assert client.portal.call(backfill.count_candidates) == 2
    assert client.portal.call(backfill.drain) == 2
    rows = _thumbnail_rows(owner_engine)
    assert rows[int(mine["id"])]["status"] == "ready"
    assert rows[int(theirs["id"])]["status"] == "ready"
    assert int(notes["id"]) not in rows
    assert client.portal.call(backfill.drain) == 0

    restored = client.get(f"/api/v1/files/{mine['id']}").json()["thumbnail"]
    assert restored is not None


@pytest.mark.usefixtures("vision")
def test_backfill_stops_after_the_attempt_limit(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    file = _upload(client, "/photos/flaky.png", _png(64, 64), "image/png")

    def broken(data: bytes, extension: str) -> RenderedThumbnail | None:
        del data, extension
        raise ThumbnailRenderError("image_unreadable")

    client.app.state.thumbnail_renderer = broken
    with owner_engine.begin() as connection:
        connection.execute(text("DELETE FROM file_thumbnail"))
    backfill = build_thumbnail_backfill(client.app.state, client.app.state.db)
    for _ in range(5):
        client.portal.call(backfill.drain)
    row = _thumbnail_rows(owner_engine)[int(file["id"])]
    assert row["status"] == "failed"
    assert row["attempts"] == 3


@pytest.mark.usefixtures("vision")
def test_other_accounts_cannot_read_a_thumbnail(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    file = _upload(client, "/photos/private.png", _png(200, 200), "image/png")
    version = file["thumbnail"]["version"]
    assert thumbnail_version("a" * 64) == "a" * 16

    member = user_client_factory()
    denied = member.client.get(
        f"/api/v1/files/{file['id']}/thumbnail",
        params={"v": version},
    )
    assert denied.status_code == 404
    assert denied.json()["error"] == "file_not_found"


@pytest.mark.usefixtures("vision")
def test_rls_hides_thumbnail_rows_from_other_accounts(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
    owner_engine: Engine,
) -> None:
    _upload(client, "/photos/rls.png", _png(120, 90), "image/png")
    member = user_client_factory()
    with rls_connection(owner_engine, user_id=member.user_id, role="user") as connection:
        hidden = connection.execute(text("SELECT count(*) FROM file_thumbnail")).scalar_one()
    with rls_connection(owner_engine, user_id=root_account.user_id, role="root") as connection:
        visible = connection.execute(text("SELECT count(*) FROM file_thumbnail")).scalar_one()
    assert hidden == 0
    assert visible == 1


@pytest.mark.usefixtures("vision")
def test_present_resource_exposes_the_thumbnail_to_the_ui_only(client: TestClient) -> None:
    file = _upload(client, "/photos/presented.png", _png(640, 480), "image/png")
    schema = FileSchema.model_validate(file)

    class _Files:
        async def get_file(self, file_id: int) -> FileSchema:
            assert file_id == schema.id
            return schema

    @asynccontextmanager
    async def scope() -> AsyncIterator[Any]:
        yield SimpleNamespace(file_service=_Files())

    registry = AgentToolRegistry(scope)

    async def run() -> Any:
        return await registry.execute(
            "present_resource",
            {"resource_type": "file", "resource_id": schema.id},
            call_id="call-1",
            max_chars=4000,
        )

    outcome = client.portal.call(run)
    assert outcome.status == "ok", outcome.content
    assert outcome.resource is not None
    assert outcome.resource["thumbnail"] == file["thumbnail"]
    assert file["thumbnail"]["version"] not in outcome.content
