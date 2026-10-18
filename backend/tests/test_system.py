"""Health, gzip, cache invalidation, settings, and standalone media."""

import base64

from fastapi.testclient import TestClient

from tests.helpers import create_text

# A 1x1 blue PNG; enough to exercise decoding, visual features, and storage.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_health_gzip_and_cache_invalidation(anonymous_client: TestClient) -> None:
    client = anonymous_client

    status = client.get("/api/v1/auth/status")
    assert status.status_code == 200
    assert status.json()["requires_setup"] is True
    assert status.json()["authenticated"] is False
    assert client.get("/api/v1/stats").status_code == 401
    assert client.get("/api/v1/health").status_code == 200

    password = "correct-horse-battery"
    setup = client.post(
        "/api/v1/auth/setup",
        json={
            "username": "owner",
            "password": password,
            "confirm_password": password,
        },
    )
    assert setup.status_code == 201, setup.text
    assert setup.json()["user"]["username"] == "owner"
    assert client.get("/api/v1/auth/status").json()["authenticated"] is True

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/stats").status_code == 401

    wrong = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"] == "invalid_credentials"

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": password},
    )
    assert login.status_code == 200
    assert client.get("/api/v1/stats").status_code == 200

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["ai"] == "missing"

    before = client.get("/api/v1/stats").json()
    assert before["file_count"] == 0

    compressed = client.get(
        "/api/v1/stats",
        headers={"Accept-Encoding": "gzip"},
    )
    assert compressed.status_code == 200
    assert compressed.headers.get("content-encoding") == "gzip"

    create_text(
        client,
        "/cache/invalidation.md",
        "A file that must invalidate the stats cache.",
        "2026-09-07T09:00:00Z",
    )
    after = client.get("/api/v1/stats").json()
    assert after["file_count"] == 1
    assert after["chunk_count"] >= 1

    settings = client.get("/api/v1/settings/ai")
    assert settings.status_code == 200
    initial = settings.json()
    assert initial["chat"]["configured"] is False
    assert initial["chat"]["key_source"] == "none"
    assert initial["embedding"]["provider"] == "hashing"
    assert initial["embedding"]["configured"] is True

    secret = "sk-test-secret-1234"
    updated = client.put(
        "/api/v1/settings/ai/chat",
        json={
            "provider": "deepseek",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "api_key": secret,
            "enabled": True,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["chat"]["configured"] is True
    assert updated_body["chat"]["source"] == "database"
    assert updated_body["chat"]["key_source"] == "database"
    assert updated_body["chat"]["key_hint"] == "...1234"
    assert secret not in updated.text

    persisted = client.get("/api/v1/settings/ai")
    assert persisted.json()["chat"]["configured"] is True
    assert secret not in persisted.text

    cleared = client.delete("/api/v1/settings/ai/chat/key")
    assert cleared.status_code == 200
    assert cleared.json()["chat"]["configured"] is False
    assert cleared.json()["chat"]["key_hint"] is None
    assert cleared.json()["chat"]["key_source"] == "none"

    media = client.post(
        "/api/v1/media",
        data={
            "path": "/media/blue-square.png",
            "caption": "A blue square used for the media smoke test.",
            "tags": "blue,square",
        },
        files={"file": ("blue-square.png", BLUE_PNG, "image/png")},
    )
    assert media.status_code == 201, media.text
    media_body = media.json()
    media_id = media_body["media_id"]
    assert media_body["caption"].startswith("A blue square")
    assert media_body["width"] == 1
    assert media_body["height"] == 1

    listed = client.get("/api/v1/media")
    assert listed.status_code == 200
    assert listed.json()["total_results"] == 1

    found = client.get("/api/v1/media/search", params={"query": "blue"})
    assert found.status_code == 200
    assert found.json()["results"][0]["media_id"] == media_id

    content = client.get(f"/api/v1/media/{media_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")
    assert content.content == BLUE_PNG

    similar = client.post(
        "/api/v1/media/search/image",
        files={"file": ("query.png", BLUE_PNG, "image/png")},
    )
    assert similar.status_code == 200
    assert similar.json()["results"][0]["media_id"] == media_id

    deleted = client.delete(f"/api/v1/media/{media_id}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/media").json()["total_results"] == 0

