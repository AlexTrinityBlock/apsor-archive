"""Chat companion API, frame processing, RLS isolation, and the agent tool."""

from collections.abc import Callable
from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, text

from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.companion.domain.companion_domain import (
    FRAME_MAX_ENCODED_BYTES,
    MAX_COMPANIONS_PER_ACCOUNT,
    MAX_FRAMES_PER_ACTION,
    parse_selection,
)
from tests.conftest import UserClient, rls_connection

BASE = "/api/v1/companions"


def _png(width: int = 800, height: int = 1200, *, alpha: bool = True) -> bytes:
    mode = "RGBA" if alpha else "RGB"
    color = (180, 40, 90, 200) if alpha else (30, 120, 200)
    image = Image.new(mode, (width, height), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _jpeg_with_exif(width: int = 600, height: int = 400) -> bytes:
    image = Image.new("RGB", (width, height), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise.
    exif[0x010F] = "SecretCamera"
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif.tobytes())
    return output.getvalue()


def _create(client: TestClient, name: str = "Elise", gender: str | None = "female") -> int:
    response = client.post(BASE, json={"name": name, "gender": gender})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _upload(
    client: TestClient,
    companion_id: int,
    action: str,
    images: list[bytes],
) -> Any:
    files = [
        ("files", (f"frame-{index}.png", data, "image/png")) for index, data in enumerate(images)
    ]
    return client.post(f"{BASE}/{companion_id}/frames", data={"action": action}, files=files)


def test_companion_crud_and_frame_processing(client: TestClient) -> None:
    """Create, upload, read back as WebP, reorder, delete a frame, then delete."""
    assert client.get(BASE).json()["resources"] == []
    companion_id = _create(client)

    uploaded = _upload(client, companion_id, "thinking", [_png(), _png(300, 300, alpha=False)])
    assert uploaded.status_code == 201, uploaded.text
    frames = uploaded.json()["frames"]
    assert [frame["position"] for frame in frames] == [0, 1]
    first, second = frames
    assert first["action"] == "thinking"
    assert (first["width"], first["height"]) == (384, 576)
    assert (second["width"], second["height"]) == (300, 300)
    assert first["size_bytes"] <= FRAME_MAX_ENCODED_BYTES

    image = client.get(first["url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in image.headers["content-security-policy"]
    assert image.headers["cache-control"] == "private, max-age=31536000, immutable"
    decoded = Image.open(BytesIO(image.content))
    assert decoded.format == "WEBP"
    assert decoded.mode == "RGBA"

    unversioned = client.get(f"{BASE}/{companion_id}/frames/{first['id']}/image")
    assert unversioned.headers["cache-control"] == "private, no-cache"
    etag = image.headers["etag"]
    cached = client.get(first["url"], headers={"If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag

    reordered = client.put(
        f"{BASE}/{companion_id}/frames/order",
        json={"action": "thinking", "frame_ids": [second["id"], first["id"]]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [frame["id"] for frame in reordered.json()["frames"]] == [second["id"], first["id"]]

    partial = client.put(
        f"{BASE}/{companion_id}/frames/order",
        json={"action": "thinking", "frame_ids": [second["id"]]},
    )
    assert partial.status_code == 422
    assert partial.json()["error"] == "companion_invalid"

    deleted = client.delete(f"{BASE}/{companion_id}/frames/{second['id']}")
    assert deleted.status_code == 204
    remaining = client.get(BASE).json()["resources"][0]["frames"]
    assert [(frame["id"], frame["position"]) for frame in remaining] == [(first["id"], 0)]
    assert client.get(f"{BASE}/{companion_id}/frames/{second['id']}/image").status_code == 404

    renamed = client.patch(
        f"{BASE}/{companion_id}", json={"name": "  Elise   Grey ", "gender": None}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Elise Grey"
    assert renamed.json()["gender"] is None

    assert client.delete(f"{BASE}/{companion_id}").status_code == 204
    assert client.get(BASE).json()["resources"] == []
    assert client.get(first["url"]).status_code == 404


def test_frame_strips_metadata_and_applies_orientation(client: TestClient) -> None:
    """EXIF orientation is applied and no EXIF survives the WebP re-encode."""
    companion_id = _create(client)
    response = client.post(
        f"{BASE}/{companion_id}/frames",
        data={"action": "idle"},
        files=[("files", ("photo.jpg", _jpeg_with_exif(), "image/jpeg"))],
    )
    assert response.status_code == 201, response.text
    frame = response.json()["frames"][0]
    assert (frame["width"], frame["height"]) == (384, 576)
    decoded = Image.open(BytesIO(client.get(frame["url"]).content))
    assert decoded.size == (384, 576)
    assert not decoded.getexif()
    assert "exif" not in decoded.info


def test_frame_validation_and_limits(client: TestClient) -> None:
    """Reject bad images, unknown actions, oversized uploads, and too many frames."""
    companion_id = _create(client)

    not_image = client.post(
        f"{BASE}/{companion_id}/frames",
        data={"action": "idle"},
        files=[("files", ("note.png", b"not an image", "image/png"))],
    )
    assert not_image.status_code == 422
    assert not_image.json()["error"] == "companion_frame_unsupported"

    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    gif_response = _upload(client, companion_id, "idle", [gif.getvalue()])
    assert gif_response.json()["error"] == "companion_frame_unsupported"

    unknown_action = _upload(client, companion_id, "dancing", [_png(20, 20)])
    assert unknown_action.status_code == 400
    assert unknown_action.json()["error"] == "invalid_request"

    oversized = client.post(
        f"{BASE}/{companion_id}/frames",
        data={"action": "idle"},
        files=[("files", ("big.png", b"\x89PNG" + b"0" * (8 * 1024 * 1024), "image/png"))],
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"] == "companion_frame_too_large"

    huge_header = BytesIO()
    Image.new("L", (8000, 6000)).save(huge_header, format="PNG")
    bomb = _upload(client, companion_id, "idle", [huge_header.getvalue()])
    assert bomb.status_code == 422
    assert bomb.json()["error"] == "companion_frame_unsupported"

    tiny = _png(16, 16)
    filled = _upload(client, companion_id, "success", [tiny] * MAX_FRAMES_PER_ACTION)
    assert filled.status_code == 201, filled.text
    overflow = _upload(client, companion_id, "success", [tiny])
    assert overflow.status_code == 409
    assert overflow.json()["error"] == "companion_frame_limit"
    other_action = _upload(client, companion_id, "confused", [tiny])
    assert other_action.status_code == 201

    blank_name = client.post(BASE, json={"name": "   "})
    assert blank_name.status_code == 400
    extra = client.post(BASE, json={"name": "A", "role": "x"})
    assert extra.status_code == 400

    for index in range(MAX_COMPANIONS_PER_ACCOUNT - 1):
        _create(client, name=f"Companion {index}")
    limit = client.post(BASE, json={"name": "One too many"})
    assert limit.status_code == 409
    assert limit.json()["error"] == "companion_limit"


def test_companion_preference_round_trip(client: TestClient) -> None:
    """Defaults, partial updates, validation, and fallback after deletion."""
    default = client.get(f"{BASE}/preference")
    assert default.status_code == 200, default.text
    assert default.json() == {
        "selected": None,
        "enabled": True,
        "motion": "full",
        "position": None,
        "updated_at": None,
    }

    preset = client.patch(
        f"{BASE}/preference",
        json={"selected": "preset:archivist-elise", "position": {"x": 0.9, "y": 0.7}},
    )
    assert preset.status_code == 200, preset.text
    body = preset.json()
    assert body["selected"] == "preset:archivist-elise"
    assert body["position"] == {"x": 0.9, "y": 0.7}
    assert body["enabled"] is True

    motion = client.patch(f"{BASE}/preference", json={"motion": "reduced", "enabled": False})
    assert motion.json()["selected"] == "preset:archivist-elise"
    assert motion.json()["motion"] == "reduced"
    assert motion.json()["enabled"] is False

    for invalid in (
        {"selected": "preset:Bad Id"},
        {"selected": "custom:abc"},
        {"selected": "other:1"},
        {"motion": "wild"},
        {"enabled": None},
        {"position": {"x": 1.5, "y": 0}},
    ):
        response = client.patch(f"{BASE}/preference", json=invalid)
        assert response.status_code == 400, invalid
        assert response.json()["error"] == "invalid_request"

    missing_custom = client.patch(f"{BASE}/preference", json={"selected": "custom:999999"})
    assert missing_custom.status_code == 422
    assert missing_custom.json()["error"] == "companion_invalid"

    companion_id = _create(client)
    custom = client.patch(f"{BASE}/preference", json={"selected": f"custom:{companion_id}"})
    assert custom.json()["selected"] == f"custom:{companion_id}"
    client.delete(f"{BASE}/{companion_id}")
    assert client.get(f"{BASE}/preference").json()["selected"] is None

    cleared = client.patch(f"{BASE}/preference", json={"position": None})
    assert cleared.json()["position"] is None


def test_companions_are_private_per_account(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
    owner_engine: Engine,
) -> None:
    """Another account sees nothing and gets 404 for every owned id."""
    companion_id = _create(client)
    frame = _upload(client, companion_id, "idle", [_png(40, 40)]).json()["frames"][0]
    client.patch(f"{BASE}/preference", json={"selected": f"custom:{companion_id}"})

    other = user_client_factory().client
    assert other.get(BASE).json()["resources"] == []
    assert other.get(frame["url"]).status_code == 404
    assert other.get(frame["url"]).json()["error"] == "companion_frame_not_found"
    assert other.patch(f"{BASE}/{companion_id}", json={"name": "Stolen"}).status_code == 404
    assert other.delete(f"{BASE}/{companion_id}").status_code == 404
    assert other.delete(f"{BASE}/{companion_id}/frames/{frame['id']}").status_code == 404
    assert _upload(other, companion_id, "idle", [_png(20, 20)]).status_code == 404
    reorder = other.put(
        f"{BASE}/{companion_id}/frames/order",
        json={"action": "idle", "frame_ids": [frame["id"]]},
    )
    assert reorder.status_code == 404
    hijack = other.patch(f"{BASE}/preference", json={"selected": f"custom:{companion_id}"})
    assert hijack.status_code == 422
    assert other.get(f"{BASE}/preference").json()["selected"] is None

    with owner_engine.connect() as connection:
        owner_id = connection.execute(text("SELECT user_id FROM companion")).scalar_one()
        other_id = connection.execute(
            text("SELECT id FROM app_user WHERE id <> :owner"), {"owner": owner_id}
        ).scalar_one()
    for table in ("companion", "companion_frame", "companion_preference"):
        with rls_connection(owner_engine, user_id=other_id, role="user") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        with rls_connection(owner_engine, user_id=owner_id, role="root") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1


def test_parse_selection() -> None:
    """Only well-formed preset and custom references parse."""
    assert parse_selection("preset:archivist-elise") is not None
    assert parse_selection("custom:12") is not None
    for value in ("preset:", "preset:-x", "custom:0", "custom:-1", "custom:1e3", "x", "preset:A"):
        assert parse_selection(value) is None, value


def test_companion_action_tool(client: TestClient) -> None:
    """The model can trigger a gesture; invalid actions are tool errors."""
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "companion_action",
                {"action": "success", "note": "Found it!"},
                call_id="call_companion_1",
            ),
            tool_call_result(
                "companion_action",
                {"action": "moonwalk"},
                call_id="call_companion_2",
            ),
            text_result("Done."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    created = client.post("/api/v1/agent/conversations", json={"title": "Companion"})
    conversation_id = created.json()["id"]
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Celebrate."},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    results = [entry for entry in response.json()["entries"] if entry["kind"] == "pi.tool-result"]
    performed, rejected = results
    assert performed["data"]["tool"] == "companion_action"
    assert performed["data"]["status"] == "ok"
    assert performed["data"]["ok"] is True
    assert performed["data"]["action"] == "success"
    assert performed["data"]["note"] == "Found it!"
    assert (
        '<companion_action action="success" status="performed"/>'
        in (performed["model"][0]["content"])
    )
    assert rejected["data"]["status"] == "error"
    assert rejected["data"]["error_code"] == "invalid_tool_arguments"

    catalog = client.get("/api/v1/agent/tools").json()
    tool = next(item for item in catalog["tools"] if item["name"] == "companion_action")
    assert tool["requires_confirmation"] is False
    assert tool["parameters"]["required"] == ["action"]
    assert "sleeping" in tool["parameters"]["properties"]["action"]["enum"]
