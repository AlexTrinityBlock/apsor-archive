"""Ordered provider chains through the root registry API."""

from typing import Any

from fastapi.testclient import TestClient

from app.infrastructure.ai.anthropic_client import AnthropicClient


def _capability(registry: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in registry["capabilities"] if item["capability"] == name)


def _active_ids(group: dict[str, Any]) -> list[int]:
    return [item["id"] for item in group["chain"]]


def _chat_row(
    client: TestClient,
    *,
    label: str,
    activate: bool = True,
    model: str = "deepseek-chat",
    api_key: str = "sk-chain-key-1234",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "deepseek",
            "label": label,
            "model": model,
            "base_url": "https://api.deepseek.com",
            "api_key": api_key,
            "activate": activate,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _row_id(group: dict[str, Any], label: str) -> int:
    return int(next(item["id"] for item in group["providers"] if item["label"] == label))


def test_create_and_activate_append_and_renumber(client: TestClient) -> None:
    first = _chat_row(client, label="first")
    chat = _capability(first, "chat")
    first_id = _row_id(chat, "first")
    assert _active_ids(chat) == [first_id]

    second = _chat_row(client, label="second")
    chat = _capability(second, "chat")
    second_id = _row_id(chat, "second")
    assert _active_ids(chat) == [first_id, second_id]
    assert [item["priority"] for item in chat["chain"]] == [0, 1]
    assert chat["active"]["id"] == first_id

    third = _chat_row(client, label="third")
    chat = _capability(third, "chat")
    third_id = _row_id(chat, "third")
    assert _active_ids(chat) == [first_id, second_id, third_id]
    assert [item["priority"] for item in chat["chain"]] == [0, 1, 2]
    assert [item["priority"] for item in chat["providers"] if item["is_active"]] == [
        0,
        1,
        2,
    ]

    # Make the last row primary; the others keep their relative order.
    reordered = client.post(
        f"/api/v1/settings/providers/chat/{third_id}/activate",
        params={"priority": 0},
    )
    assert reordered.status_code == 200, reordered.text
    chat = _capability(reordered.json(), "chat")
    assert _active_ids(chat) == [third_id, first_id, second_id]
    assert [item["priority"] for item in chat["chain"]] == [0, 1, 2]
    assert chat["active"]["id"] == third_id

    # Per-row deactivation closes the gap without disturbing the rest.
    removed = client.post(
        f"/api/v1/settings/providers/chat/{first_id}/deactivate"
    )
    assert removed.status_code == 200, removed.text
    chat = _capability(removed.json(), "chat")
    assert _active_ids(chat) == [third_id, second_id]
    assert [item["priority"] for item in chat["chain"]] == [0, 1]

    # Deleting the active primary promotes the next row and renumbers it.
    deleted = client.delete(f"/api/v1/settings/providers/chat/{third_id}")
    assert deleted.status_code == 200, deleted.text
    chat = _capability(deleted.json(), "chat")
    assert _active_ids(chat) == [second_id]
    assert chat["active"]["id"] == second_id
    assert chat["chain"][0]["priority"] == 0

    # The capability-wide endpoint clears the whole chain.
    cleared = client.post("/api/v1/settings/providers/chat/deactivate")
    assert cleared.status_code == 200, cleared.text
    chat = _capability(cleared.json(), "chat")
    assert chat["chain"] == []
    assert chat["active"]["id"] is None
    assert all(item["is_active"] is False for item in chat["providers"])


def test_create_inactive_stays_out_of_the_chain(client: TestClient) -> None:
    saved = _chat_row(client, label="saved only", activate=False)
    chat = _capability(saved, "chat")
    saved_id = _row_id(chat, "saved only")
    assert chat["chain"] == []
    assert chat["active"]["id"] is None
    assert all(item["is_active"] is False for item in chat["providers"])

    appended = client.post(f"/api/v1/settings/providers/chat/{saved_id}/activate")
    assert appended.status_code == 200, appended.text
    chat = _capability(appended.json(), "chat")
    assert _active_ids(chat) == [saved_id]
    assert chat["active"]["id"] == saved_id


def test_embedding_chain_requires_one_model_and_dimension(client: TestClient) -> None:
    first = client.post(
        "/api/v1/settings/providers/embedding",
        json={
            "provider": "openai-compatible",
            "label": "embedding primary",
            "model": "text-embedding-3-small",
            "dimension": 384,
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-embed-primary-1234",
        },
    )
    assert first.status_code == 200, first.text
    group = _capability(first.json(), "embedding")
    primary_id = _row_id(group, "embedding primary")
    assert _active_ids(group) == [primary_id]
    assert group["chain"][0]["priority"] == 0

    same = client.post(
        "/api/v1/settings/providers/embedding",
        json={
            "provider": "openai-compatible",
            "label": "embedding backup",
            "model": "text-embedding-3-small",
            "dimension": 384,
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-embed-backup-5678",
        },
    )
    assert same.status_code == 200, same.text
    group = _capability(same.json(), "embedding")
    backup_id = _row_id(group, "embedding backup")
    assert _active_ids(group) == [primary_id, backup_id]

    mismatch = client.post(
        "/api/v1/settings/providers/embedding",
        json={
            "provider": "openai-compatible",
            "label": "different dimension",
            "model": "text-embedding-3-small",
            "dimension": 1536,
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-embed-wrong-9012",
        },
    )
    assert mismatch.status_code == 422, mismatch.text
    body = mismatch.json()
    assert body["error"] == "invalid_provider_config"
    assert "vector index" in body["detail"]
    assert "dimension" in body["detail"]
    # The rejected insert is rolled back, not left as a hidden saved row.
    registry = client.get("/api/v1/settings/providers")
    assert registry.status_code == 200
    group = _capability(registry.json(), "embedding")
    assert [item["label"] for item in group["providers"]] == [
        "embedding primary",
        "embedding backup",
    ]

    # A saved mismatched row can exist, but activating it later is rejected.
    saved_mismatch = client.post(
        "/api/v1/settings/providers/embedding",
        json={
            "provider": "openai",
            "label": "saved different model",
            "model": "text-embedding-3-large",
            "dimension": 384,
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-embed-wrong-3456",
            "activate": False,
        },
    )
    assert saved_mismatch.status_code == 200, saved_mismatch.text
    group = _capability(saved_mismatch.json(), "embedding")
    mismatch_id = _row_id(group, "saved different model")
    rejected = client.post(
        f"/api/v1/settings/providers/embedding/{mismatch_id}/activate"
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "invalid_provider_config"
    group = _capability(client.get("/api/v1/settings/providers").json(), "embedding")
    assert _active_ids(group) == [primary_id, backup_id]


def test_anthropic_row_is_accepted_and_builds_the_native_client(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "anthropic",
            "label": "Claude primary",
            "model": "claude-haiku-5-5",
            "api_key": "sk-ant-chain-1234",
            "max_output_tokens": 64_000,
        },
    )
    assert response.status_code == 200, response.text
    group = _capability(response.json(), "chat")
    active = group["active"]
    assert active["provider"] == "anthropic"
    # No base URL was sent, so the provider-specific default applies.
    assert active["base_url"] == "https://api.anthropic.com"
    assert active["max_output_tokens"] == 64_000
    assert active["configured"] is True
    assert active["key_hint"] == "...1234"
    assert "anthropic" in group["allowed_providers"]

    runtime = client.app.state.ai_runtime
    assert isinstance(runtime.text_generator, AnthropicClient)
    assert runtime.text_generator.max_output_tokens == 64_000
    assert runtime.text_generator.reasoning_effort is None


def test_anthropic_row_accepts_a_deepseek_compatible_base_url(
    client: TestClient,
) -> None:
    """The compatible origin is a legal row value, not a provider default."""
    response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "anthropic",
            "label": "Claude-compatible DeepSeek",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com/anthropic",
            "api_key": "sk-ant-compatible-5678",
        },
    )

    assert response.status_code == 200, response.text
    group = _capability(response.json(), "chat")
    assert group["active"]["provider"] == "anthropic"
    assert group["active"]["base_url"] == "https://api.deepseek.com/anthropic"


def test_chat_max_output_tokens_round_trips_through_the_registry(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": "deepseek",
            "label": "capped chat",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-cap-key-1234",
            "max_output_tokens": 64_000,
        },
    )
    assert created.status_code == 200, created.text
    group = _capability(created.json(), "chat")
    row_id = _row_id(group, "capped chat")
    assert group["providers"][0]["max_output_tokens"] == 64_000

    updated = client.put(
        f"/api/v1/settings/providers/chat/{row_id}",
        json={
            "provider": "deepseek",
            "label": "capped chat",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "max_output_tokens": 32_000,
        },
    )
    assert updated.status_code == 200, updated.text
    group = _capability(updated.json(), "chat")
    assert group["active"]["max_output_tokens"] == 32_000

    cleared = client.put(
        f"/api/v1/settings/providers/chat/{row_id}",
        json={
            "provider": "deepseek",
            "label": "capped chat",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "max_output_tokens": None,
        },
    )
    assert cleared.status_code == 200, cleared.text
    group = _capability(cleared.json(), "chat")
    assert group["active"]["max_output_tokens"] is None

    out_of_range = client.put(
        f"/api/v1/settings/providers/chat/{row_id}",
        json={
            "provider": "deepseek",
            "label": "capped chat",
            "model": "deepseek-flash",
            "base_url": "https://api.deepseek.com",
            "max_output_tokens": 128,
        },
    )
    assert out_of_range.status_code == 400, out_of_range.text
    assert out_of_range.json()["error"] == "invalid_request"
