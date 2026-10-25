"""Health, gzip, cache invalidation, and the multi-provider registry."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.module.knowledge.domain.provider_config_domain import ProviderCapability
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.provider_tester_protocol import ProviderTestOutcome
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import create_text


class FakeProviderTester:
    """Deterministic provider probe that never opens an external connection."""

    def __init__(self) -> None:
        self.calls: list[tuple[ProviderCapability, ProviderConfig]] = []

    async def test(
        self,
        capability: ProviderCapability,
        config: ProviderConfig,
    ) -> ProviderTestOutcome:
        self.calls.append((capability, config))
        return ProviderTestOutcome(
            ok=True,
            detail=f"fake {capability} connection ok",
        )


def _capability(registry: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in registry["capabilities"] if item["capability"] == name)


def _active_ids(group: dict[str, Any]) -> list[int]:
    return [item["id"] for item in group["providers"] if item["is_active"]]


def test_health_gzip_and_cache_invalidation(anonymous_client: TestClient) -> None:
    client = anonymous_client
    tester = FakeProviderTester()
    client.app.state.provider_tester = tester

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

    profile = client.patch(
        "/api/v1/auth/me",
        json={
            "display_name": "Alex",
            "bio": "I keep notes, memories, and the occasional argument with a wrench.",
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["username"] == "owner"
    assert profile.json()["display_name"] == "Alex"
    assert "wrench" in profile.json()["bio"]
    auth_status = client.get("/api/v1/auth/status").json()
    assert auth_status["user"]["display_name"] == "Alex"
    assert auth_status["user"]["bio"] == profile.json()["bio"]
    invalid_profile = client.patch(
        "/api/v1/auth/me",
        json={"display_name": "   ", "bio": "Still here."},
    )
    assert invalid_profile.status_code == 422
    assert invalid_profile.json()["error"] == "invalid_profile"

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["ai"] == "missing"
    assert health.json()["embedding_provider"] == "hashing"
    assert health.json()["web_search_provider"] == "none"
    assert health.json()["web_search_configured"] is False
    assert health.json()["web_fetch_provider"] == "none"
    assert health.json()["web_fetch_configured"] is False

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

    # ------------------------------------------------------------------
    # Registry initial state: four capability groups, each with one active
    # virtual fallback config and no saved DB rows yet.
    # ------------------------------------------------------------------
    initial_response = client.get("/api/v1/settings/providers")
    assert initial_response.status_code == 200, initial_response.text
    initial = initial_response.json()
    assert [group["capability"] for group in initial["capabilities"]] == [
        "chat",
        "embedding",
        "web_search",
        "web_fetch",
    ]
    initial_chat = _capability(initial, "chat")
    assert initial_chat["active"]["id"] is None
    assert initial_chat["active"]["provider"] == "deepseek"
    assert initial_chat["active"]["configured"] is False
    assert initial_chat["providers"] == []
    assert initial_chat["allowed_providers"] == [
        "deepseek",
        "none",
        "openai-compatible",
    ]
    assert initial_chat["default_base_url"] == "https://api.deepseek.com"
    assert initial_chat["supports_model"] is True
    assert initial_chat["supports_dimension"] is False
    assert _capability(initial, "embedding")["active"]["provider"] == "hashing"
    assert _capability(initial, "embedding")["active"]["configured"] is True
    for web_capability in ("web_search", "web_fetch"):
        web_group = _capability(initial, web_capability)
        assert web_group["active"]["provider"] == "none"
        assert web_group["active"]["configured"] is False
        assert web_group["allowed_providers"] == ["none", "tavily"]
        assert web_group["default_base_url"] == "https://api.tavily.com"
        assert web_group["supports_model"] is False
        assert web_group["supports_dimension"] is False

    # ------------------------------------------------------------------
    # Create two chat providers: the first is active immediately, the second
    # is saved inactive. Only one row may be active at a time.
    # ------------------------------------------------------------------
    first_secret = "sk-chat-first-1234"
    first_response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "deepseek",
            "label": "Primary chat",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key": first_secret,
        },
    )
    assert first_response.status_code == 200, first_response.text
    assert first_secret not in first_response.text
    first_registry = first_response.json()
    first_chat_group = _capability(first_registry, "chat")
    first_id = first_chat_group["active"]["id"]
    assert isinstance(first_id, int)
    assert first_chat_group["active"]["key_hint"] == "...1234"
    assert first_chat_group["active"]["key_source"] == "database"
    assert first_chat_group["active"]["configured"] is True
    assert _active_ids(first_chat_group) == [first_id]

    second_secret = "sk-chat-second-5678"
    second_response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "deepseek",
            "label": "Secondary chat",
            "model": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": second_secret,
            "activate": False,
        },
    )
    assert second_response.status_code == 200, second_response.text
    second_chat_group = _capability(second_response.json(), "chat")
    second_id = next(
        item["id"] for item in second_chat_group["providers"] if item["label"] == "Secondary chat"
    )
    assert second_id > first_id
    assert _active_ids(second_chat_group) == [first_id]
    assert second_chat_group["active"]["label"] == "Primary chat"
    assert all(secret not in second_response.text for secret in (first_secret, second_secret))

    activated = client.post(f"/api/v1/settings/providers/chat/{second_id}/activate")
    assert activated.status_code == 200, activated.text
    activated_chat = _capability(activated.json(), "chat")
    assert activated_chat["active"]["id"] == second_id
    assert _active_ids(activated_chat) == [second_id]

    # Editing an inactive provider must never activate it implicitly:
    # ProviderUpdateSchema.activate defaults to false.
    inactive_edit = client.put(
        f"/api/v1/settings/providers/chat/{first_id}",
        json={
            "provider": "deepseek",
            "label": "Primary edited while inactive",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-chat-inactive-7890",
        },
    )
    assert inactive_edit.status_code == 200, inactive_edit.text
    inactive_group = _capability(inactive_edit.json(), "chat")
    inactive_row = next(item for item in inactive_group["providers"] if item["id"] == first_id)
    assert inactive_row["is_active"] is False
    assert inactive_row["label"] == "Primary edited while inactive"
    assert inactive_group["active"]["id"] == second_id
    assert _active_ids(inactive_group) == [second_id]

    # Editing the active row keeps it active, but `activate` still defaults to
    # false so the write never touches other rows' active state.
    edited_secret = "sk-chat-edited-9012"
    edited = client.put(
        f"/api/v1/settings/providers/chat/{second_id}",
        json={
            "provider": "deepseek",
            "label": "  Secondary edited  ",
            "model": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": edited_secret,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited_secret not in edited.text
    edited_chat = _capability(edited.json(), "chat")
    edited_active = edited_chat["active"]
    assert edited_active["id"] == second_id
    assert edited_active["label"] == "Secondary edited"
    assert edited_active["model"] == "deepseek-reasoner"
    assert edited_active["base_url"] == "https://api.deepseek.com/v1"
    assert edited_active["key_hint"] == "...9012"
    assert edited_active["key_source"] == "database"
    assert edited_active["is_active"] is True
    assert _active_ids(edited_chat) == [second_id]

    cleared = client.put(
        f"/api/v1/settings/providers/chat/{second_id}",
        json={
            "provider": "deepseek",
            "label": "Secondary edited",
            "model": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "clear_api_key": True,
        },
    )
    assert cleared.status_code == 200, cleared.text
    cleared_chat = _capability(cleared.json(), "chat")
    assert cleared_chat["active"]["id"] == second_id
    assert cleared_chat["active"]["key_hint"] is None
    assert cleared_chat["active"]["key_source"] == "none"
    assert cleared_chat["active"]["configured"] is False
    assert cleared_chat["active"]["is_active"] is True
    assert _active_ids(cleared_chat) == [second_id]

    # ------------------------------------------------------------------
    # Tavily web_search and web_fetch are independent rows in two physical
    # tables. Both keys are stored separately and never returned.
    # ------------------------------------------------------------------
    search_secret = "tvly-search-secret-1111"
    search_response = client.post(
        "/api/v1/settings/providers/web_search",
        json={
            "provider": "tavily",
            "label": "Tavily search",
            "api_key": search_secret,
        },
    )
    assert search_response.status_code == 200, search_response.text
    assert search_secret not in search_response.text
    search_group = _capability(search_response.json(), "web_search")
    search_id = search_group["active"]["id"]
    assert search_group["active"]["provider"] == "tavily"
    assert search_group["active"]["model"] is None
    assert search_group["active"]["dimension"] is None
    assert search_group["active"]["base_url"] == "https://api.tavily.com"
    assert search_group["active"]["key_hint"] == "...1111"

    fetch_secret = "tvly-fetch-secret-5678"
    fetch_response = client.post(
        "/api/v1/settings/providers/web_fetch",
        json={
            "provider": "tavily",
            "label": "Tavily fetch",
            "api_key": fetch_secret,
        },
    )
    assert fetch_response.status_code == 200, fetch_response.text
    assert fetch_secret not in fetch_response.text
    fetch_group = _capability(fetch_response.json(), "web_fetch")
    fetch_id = fetch_group["active"]["id"]
    assert fetch_group["active"]["provider"] == "tavily"
    assert fetch_group["active"]["key_hint"] == "...5678"
    assert isinstance(search_id, int)
    assert isinstance(fetch_id, int)

    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        row_counts = {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in (
                "chat_provider_config",
                "embedding_provider_config",
                "web_search_provider_config",
                "web_fetch_provider_config",
            )
        }
        assert row_counts == {
            "chat_provider_config": 2,
            "embedding_provider_config": 0,
            "web_search_provider_config": 1,
            "web_fetch_provider_config": 1,
        }
        assert (
            connection.execute(
                text("SELECT to_regclass('public.ai_provider_config')")
            ).scalar_one_or_none()
            is None
        )
    engine.dispose()

    # A provider connection test goes through the injected fake and receives
    # the plaintext key only server-side; no secret crosses the HTTP boundary.
    tested = client.post(f"/api/v1/settings/providers/web_fetch/{fetch_id}/test")
    assert tested.status_code == 200, tested.text
    tested_body = tested.json()
    assert tested_body["ok"] is True
    assert tested_body["capability"] == "web_fetch"
    assert tested_body["provider_id"] == fetch_id
    assert tested_body["provider"] == "tavily"
    assert tested_body["label"] == "Tavily fetch"
    assert tested_body["detail"] == "fake web_fetch connection ok"
    assert tested_body["latency_ms"] >= 0
    assert fetch_secret not in tested.text
    assert tester.calls[-1][0] == "web_fetch"
    assert tester.calls[-1][1].api_key == fetch_secret

    # Deactivating the chat capability clears its active row and the runtime
    # falls back to the environment/default (unconfigured) snapshot.
    deactivated = client.post("/api/v1/settings/providers/chat/deactivate")
    assert deactivated.status_code == 200, deactivated.text
    deactivated_chat = _capability(deactivated.json(), "chat")
    assert deactivated_chat["active"]["id"] is None
    assert deactivated_chat["active"]["configured"] is False
    assert _active_ids(deactivated_chat) == []
    ai_status = client.get("/api/v1/ai/status")
    assert ai_status.status_code == 200
    assert ai_status.json()["configured"] is False
    assert ai_status.json()["provider"] == "none"
    assert ai_status.json()["web_search_configured"] is True
    assert ai_status.json()["web_fetch_configured"] is True

    # ------------------------------------------------------------------
    # Cache invalidation: a direct DB edit stays invisible while the cached
    # registry is served; the next provider write bumps the "providers"
    # version and the GET reflects the edited row.
    # ------------------------------------------------------------------
    cached_response = client.get("/api/v1/settings/providers")
    assert cached_response.status_code == 200
    cache = client.app.state.cache
    assert client.portal is not None
    version_before = client.portal.call(cache.get_version, "providers")

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE chat_provider_config SET label = :label WHERE id = :provider_id"),
            {"label": "Direct database label", "provider_id": second_id},
        )
    engine.dispose()

    stale = client.get("/api/v1/settings/providers")
    assert stale.status_code == 200
    stale_labels = [item["label"] for item in _capability(stale.json(), "chat")["providers"]]
    assert "Secondary edited" in stale_labels
    assert "Direct database label" not in stale_labels

    # Delete the inactive first chat provider; this is a write, so the cache
    # must invalidate and the direct DB label becomes visible.
    deleted = client.delete(f"/api/v1/settings/providers/chat/{first_id}")
    assert deleted.status_code == 200, deleted.text
    assert all(item["id"] != first_id for item in _capability(deleted.json(), "chat")["providers"])
    version_after = client.portal.call(cache.get_version, "providers")
    assert version_after == version_before + 1

    refreshed = client.get("/api/v1/settings/providers")
    assert refreshed.status_code == 200
    refreshed_labels = [
        item["label"] for item in _capability(refreshed.json(), "chat")["providers"]
    ]
    assert "Direct database label" in refreshed_labels

    # Identity values are never reused after a delete.
    replacement = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "deepseek",
            "label": "Replacement chat",
            "model": "deepseek-chat",
            "api_key": "sk-chat-replacement-3456",
            "activate": False,
        },
    )
    assert replacement.status_code == 200, replacement.text
    replacement_chat = _capability(replacement.json(), "chat")
    replacement_id = next(
        item["id"] for item in replacement_chat["providers"] if item["label"] == "Replacement chat"
    )
    assert replacement_id > first_id
    assert _active_ids(replacement_chat) == []
