"""Root assignment API: validation, probe gating, inheritance, and reset.

Every provider call is a deterministic fake installed on ``app.state``; the
suite never reaches a real endpoint and uses the migrated disposable database.
"""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.ai.probe import ProbeOutcome
from app.infrastructure.ai.user_models import (
    ChatAssignment,
    SlotValues,
    assignment_fingerprint,
    build_user_text_generator,
    resolve_endpoint,
    slot_values,
)
from app.module.knowledge.protocol.provider_config import ProviderConfig
from tests.conftest import UserClient


class FakeProviderProbe:
    """Deterministic probe that records every candidate it was asked to test."""

    def __init__(self, *, ok: bool = True, detail: str | None = None) -> None:
        self.ok = ok
        self.detail = detail
        self.calls: list[tuple[int | None, str, str | None]] = []

    async def probe(
        self,
        config: ProviderConfig,
        *,
        model: str,
        reasoning_effort: str | None,
    ) -> ProbeOutcome:
        self.calls.append((config.row_id, model, reasoning_effort))
        if not self.ok:
            return ProbeOutcome(
                ok=False,
                latency_ms=3,
                resolved_model=None,
                usage={},
                detail=self.detail or "the provider rejected the request",
            )
        return ProbeOutcome(
            ok=True,
            latency_ms=7,
            resolved_model=model,
            usage={"input_tokens": 5, "output_tokens": 1},
            detail=None,
        )


def _create_chat_row(
    client: TestClient,
    *,
    label: str,
    model: str = "deepseek-chat",
    api_key: str | None = "sk-assignment-key-1234",
    provider: str = "deepseek",
    base_url: str | None = "https://api.deepseek.com",
    activate: bool = True,
) -> int:
    body: dict[str, Any] = {
        "provider": provider,
        "label": label,
        "model": model,
        "base_url": base_url,
        "activate": activate,
    }
    if api_key is not None:
        body["api_key"] = api_key
    response = client.post("/api/v1/settings/providers/chat", json=body)
    assert response.status_code == 200, response.text
    chat = next(
        group
        for group in response.json()["capabilities"]
        if group["capability"] == "chat"
    )
    return int(next(item["id"] for item in chat["providers"] if item["label"] == label))


def _payload(
    primary_id: int,
    auxiliary_id: int,
    *,
    chat_model: str = "deepseek-flash",
    aux_model: str = "deepseek-flash",
    chat_effort: str | None = "high",
    aux_effort: str = "low",
    window: int | None = None,
    threshold: int | None = None,
) -> dict[str, Any]:
    return {
        "chat_provider_config_id": primary_id,
        "chat_model": chat_model,
        "chat_reasoning_effort": chat_effort,
        "aux_provider_config_id": auxiliary_id,
        "aux_model": aux_model,
        "aux_reasoning_effort": aux_effort,
        "context_window_tokens": window,
        "compaction_threshold_tokens": threshold,
    }


def _assignment_for(client: TestClient, user_id: int) -> dict[str, Any]:
    listing = client.get("/api/v1/model-assignments")
    assert listing.status_code == 200, listing.text
    return next(
        item for item in listing.json()["items"] if item["user_id"] == user_id
    )


def _stored_assignment(engine: Engine, user_id: int) -> tuple[Any, ...]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(
                    "SELECT chat_provider_config_id, chat_model, chat_reasoning_effort, "
                    "aux_provider_config_id, aux_model, aux_reasoning_effort, "
                    "chat_context_window_tokens, chat_compaction_threshold_tokens "
                    "FROM app_user WHERE id = :user_id"
                ),
                {"user_id": user_id},
            ).one()
        )


def test_non_root_cannot_write_but_can_read_me(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    primary_id = _create_chat_row(client, label="primary")
    auxiliary_id = _create_chat_row(client, label="auxiliary")
    member: UserClient = user_client_factory()
    payload = _payload(primary_id, auxiliary_id)

    writes = (
        member.client.put(
            f"/api/v1/model-assignments/{member.user_id}",
            json=payload,
        ),
        member.client.delete(f"/api/v1/model-assignments/{member.user_id}"),
        member.client.post(
            f"/api/v1/chat-endpoints/{primary_id}/probe",
            json={"model": "deepseek-flash", "reasoning_effort": "low"},
        ),
        member.client.get("/api/v1/model-assignments"),
        member.client.get("/api/v1/chat-endpoints"),
        member.client.get("/api/v1/model-catalog"),
    )
    for response in writes:
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "forbidden"

    me = member.client.get("/api/v1/model-assignments/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["user_id"] == member.user_id
    assert body["source"] == "unassigned"
    assert body["chat_provider_config_id"] is None
    assert body["aux_reasoning_effort"] == "low"


def test_unknown_model_is_accepted_verbatim_with_a_warning(
    client: TestClient,
    user_client_factory: Any,
    owner_engine: Engine,
) -> None:
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe
    primary_id = _create_chat_row(client, label="primary")
    auxiliary_id = _create_chat_row(client, label="auxiliary")
    target: UserClient = user_client_factory()

    response = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(
            primary_id,
            auxiliary_id,
            chat_model="totally-unknown-model",
            aux_model="deepseek-flash",
        ),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chat_model"] == "totally-unknown-model"
    assert body["effective_chat_model"] == "totally-unknown-model"
    assert body["chat_tier"] is None
    assert body["chat_pricing"] is None
    assert "unknown_model" in body["warnings"]
    assert body["chat_provider_label"] == "primary"
    assert body["aux_provider_label"] == "auxiliary"
    assert body["source"] == "account"
    assert body["degraded_reason"] is None
    assert probe.calls == [
        (primary_id, "totally-unknown-model", "high"),
        (auxiliary_id, "deepseek-flash", "low"),
    ]

    stored = _stored_assignment(owner_engine, target.user_id)
    assert stored[1] == "totally-unknown-model"


def test_missing_auxiliary_slot_is_a_validation_error(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    primary_id = _create_chat_row(client, label="primary")
    target: UserClient = user_client_factory()
    payload = _payload(primary_id, primary_id)
    payload.pop("aux_provider_config_id")
    payload.pop("aux_model")

    response = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=payload,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


def test_inactive_and_disabled_endpoints_are_rejected(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    active_id = _create_chat_row(client, label="active")
    inactive_id = _create_chat_row(client, label="inactive", activate=False)
    disabled_id = _create_chat_row(
        client,
        label="disabled",
        provider="none",
        model="none",
        api_key="",
        base_url=None,
    )
    target: UserClient = user_client_factory()
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe

    inactive = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(inactive_id, active_id),
    )
    assert inactive.status_code == 422, inactive.text
    assert inactive.json()["error"] == "invalid_model_assignment"
    assert "primary" in inactive.json()["detail"]

    disabled = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(active_id, disabled_id),
    )
    assert disabled.status_code == 422, disabled.text
    assert disabled.json()["error"] == "invalid_model_assignment"
    assert "auxiliary" in disabled.json()["detail"]

    keyless_id = _create_chat_row(
        client,
        label="keyless",
        provider="openai-compatible",
        model="local-model",
        api_key=None,
        base_url="https://gateway.example.com",
    )
    keyless = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(active_id, keyless_id),
    )
    assert keyless.status_code == 422, keyless.text
    assert keyless.json()["error"] == "invalid_model_assignment"
    assert "auxiliary" in keyless.json()["detail"]
    assert probe.calls == []

    missing = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(999_999, active_id),
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"] == "invalid_model_assignment"


def test_changed_slot_probes_once_and_a_budget_change_skips_the_probe(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe
    shared_id = _create_chat_row(client, label="shared")
    target: UserClient = user_client_factory()
    url = f"/api/v1/model-assignments/{target.user_id}"

    first = client.put(
        url,
        json=_payload(shared_id, shared_id, chat_effort="low", aux_effort="low"),
    )
    assert first.status_code == 200, first.text
    # Both slots point at one row, model, and effort; the connection is tested once.
    assert probe.calls == [(shared_id, "deepseek-flash", "low")]

    budget_only = client.put(
        url,
        json=_payload(
            shared_id,
            shared_id,
            chat_effort="low",
            aux_effort="low",
            window=90_000,
            threshold=85_000,
        ),
    )
    assert budget_only.status_code == 200, budget_only.text
    body = budget_only.json()
    assert body["chat_context_window_tokens"] == 90_000
    assert body["chat_compaction_threshold_tokens"] == 85_000
    assert len(probe.calls) == 1

    no_op = client.put(
        url,
        json=_payload(
            shared_id,
            shared_id,
            chat_effort="low",
            aux_effort="low",
            window=90_000,
            threshold=85_000,
        ),
    )
    assert no_op.status_code == 200, no_op.text
    assert len(probe.calls) == 1

    auxiliary_changed = client.put(
        url,
        json=_payload(
            shared_id,
            shared_id,
            aux_model="deepseek-v4-pro",
            chat_effort="low",
            aux_effort="low",
            window=90_000,
            threshold=85_000,
        ),
    )
    assert auxiliary_changed.status_code == 200, auxiliary_changed.text
    assert probe.calls == [
        (shared_id, "deepseek-flash", "low"),
        (shared_id, "deepseek-v4-pro", "low"),
    ]
    assert "unknown_model" in auxiliary_changed.json()["warnings"]


def test_failed_probe_rejects_the_whole_write_and_keeps_the_stored_row(
    client: TestClient,
    user_client_factory: Any,
    owner_engine: Engine,
) -> None:
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe
    primary_id = _create_chat_row(client, label="primary")
    auxiliary_id = _create_chat_row(client, label="auxiliary")
    target: UserClient = user_client_factory()
    url = f"/api/v1/model-assignments/{target.user_id}"

    saved = client.put(url, json=_payload(primary_id, auxiliary_id))
    assert saved.status_code == 200, saved.text
    before = _stored_assignment(owner_engine, target.user_id)

    probe.ok = False
    probe.detail = "the provider rejected the candidate model"
    failed = client.put(
        url,
        json=_payload(primary_id, auxiliary_id, chat_model="deepseek-v4-pro"),
    )
    assert failed.status_code == 422, failed.text
    assert failed.json()["error"] == "model_probe_failed"
    assert failed.json()["detail"] == (
        "primary: the provider rejected the candidate model"
    )
    assert _stored_assignment(owner_engine, target.user_id) == before

    listing = _assignment_for(client, target.user_id)
    assert listing["chat_model"] == "deepseek-flash"


def test_budget_order_violation_is_rejected(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe
    shared_id = _create_chat_row(client, label="shared")
    target: UserClient = user_client_factory()

    response = client.put(
        f"/api/v1/model-assignments/{target.user_id}",
        json=_payload(shared_id, shared_id, window=90_000, threshold=90_000),
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_model_assignment"
    assert probe.calls == []


def test_q1_shaped_null_auxiliary_inherits_the_primary(
    client: TestClient,
    user_client_factory: Any,
    owner_engine: Engine,
) -> None:
    primary_id = _create_chat_row(client, label="primary", model="deepseek-chat")
    member: UserClient = user_client_factory()
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE app_user SET chat_provider_config_id = :row_id, "
                "chat_model = :model WHERE id = :user_id"
            ),
            {
                "row_id": primary_id,
                "model": "deepseek-chat",
                "user_id": member.user_id,
            },
        )

    me = member.client.get("/api/v1/model-assignments/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["aux_provider_config_id"] is None
    assert body["aux_model"] is None
    assert body["effective_aux_model"] == "deepseek-chat"
    assert body["effective_aux_provider"] == "deepseek"
    assert body["effective_aux_effort"] == "low"
    assert body["aux_provider_label"] == "primary"
    assert body["source"] == "account"
    assert body["degraded_reason"] is None
    assert "aux_inherited_from_primary" in body["warnings"]


def test_reset_clears_every_assignment_column(
    client: TestClient,
    user_client_factory: Any,
    owner_engine: Engine,
) -> None:
    probe = FakeProviderProbe()
    client.app.state.provider_probe = probe
    primary_id = _create_chat_row(client, label="primary")
    auxiliary_id = _create_chat_row(client, label="auxiliary")
    target: UserClient = user_client_factory()
    url = f"/api/v1/model-assignments/{target.user_id}"

    saved = client.put(
        url,
        json=_payload(primary_id, auxiliary_id, window=120_000, threshold=100_000),
    )
    assert saved.status_code == 200, saved.text
    calls = len(probe.calls)

    reset = client.delete(url)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["chat_provider_config_id"] is None
    assert body["chat_model"] is None
    assert body["chat_reasoning_effort"] is None
    assert body["aux_provider_config_id"] is None
    assert body["aux_model"] is None
    assert body["aux_reasoning_effort"] == "low"
    assert body["chat_context_window_tokens"] is None
    assert body["chat_compaction_threshold_tokens"] is None
    assert body["source"] == "unassigned"
    assert body["warnings"] == []
    assert len(probe.calls) == calls
    assert _stored_assignment(owner_engine, target.user_id) == (
        None,
        None,
        None,
        None,
        None,
        "low",
        None,
        None,
    )


def test_endpoint_and_catalog_listings_never_expose_keys_or_full_urls(
    client: TestClient,
) -> None:
    secret = "sk-endpoint-secret-4321"
    row_id = _create_chat_row(
        client,
        label="primary",
        api_key=secret,
        model="claude-haiku-5-5",
    )

    endpoints = client.get("/api/v1/chat-endpoints")
    assert endpoints.status_code == 200, endpoints.text
    assert secret not in endpoints.text
    assert "https://api.deepseek.com" not in endpoints.text
    item = next(
        entry for entry in endpoints.json()["items"] if entry["id"] == row_id
    )
    assert item["base_url_host"] == "api.deepseek.com"
    assert item["key_source"] == "database"
    assert item["configured"] is True
    assert "api_key" not in item

    catalog = client.get("/api/v1/model-catalog")
    assert catalog.status_code == 200, catalog.text
    entries = {entry["model"]: entry for entry in catalog.json()["items"]}
    haiku = entries["claude-haiku-5-5"]
    assert haiku["tier"] == "economy"
    assert haiku["pricing"]["input"] == 0.1
    assert entries["deepseek-flash"]["pricing"] is None


# ---------------------------------------------------------------------------
# Resolver unit tests: no fallback, Q1 inheritance, fingerprint inputs
# ---------------------------------------------------------------------------


class _RecordingBuilder:
    def __init__(self) -> None:
        self.configs: list[ProviderConfig] = []

    def build_text_generator(self, config: ProviderConfig) -> object:
        self.configs.append(config)
        return object()


def _config(
    *,
    row_id: int | None,
    provider: str = "deepseek",
    base_url: str | None = "https://api.deepseek.com",
    api_key: str | None = "secret",
    enabled: bool = True,
    source: str = "database",
    model: str | None = "deepseek-chat",
) -> ProviderConfig:
    return ProviderConfig(
        capability="chat",
        provider=provider,
        label=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        dimension=None,
        enabled=enabled,
        source=source,  # type: ignore[arg-type]
        row_id=row_id,
    )


def test_resolve_endpoint_never_matches_an_environment_fallback() -> None:
    environment = _config(row_id=None, api_key="deployment-key", source="environment")
    assert resolve_endpoint([environment], 1) is None
    assert resolve_endpoint([environment, _config(row_id=2)], 2) is not None


def test_slot_values_inherits_only_the_q1_shape() -> None:
    assignment = ChatAssignment(
        user_id=1,
        provider_config_id=7,
        model="primary-model",
        reasoning_effort="high",
        aux_provider_config_id=None,
        aux_model=None,
        aux_reasoning_effort="low",
        context_window_tokens=None,
        compaction_threshold_tokens=None,
    )
    assert slot_values(assignment, "primary") == SlotValues(
        row_id=7,
        model="primary-model",
        effort="high",
    )
    assert slot_values(assignment, "auxiliary") == SlotValues(
        row_id=7,
        model="primary-model",
        effort="low",
        inherited=True,
    )

    deleted_auxiliary = replace(assignment, aux_model="deleted-model")
    assert slot_values(deleted_auxiliary, "auxiliary") == SlotValues(
        row_id=None,
        model="deleted-model",
        effort="low",
    )


def test_build_user_text_generator_has_no_fallback() -> None:
    builder = _RecordingBuilder()
    assignment = ChatAssignment(
        user_id=1,
        provider_config_id=7,
        model="assigned-model",
        reasoning_effort="high",
        aux_provider_config_id=8,
        aux_model="aux-model",
        aux_reasoning_effort="low",
        context_window_tokens=None,
        compaction_threshold_tokens=None,
    )

    missing = SimpleNamespace(chat_chain=(), builder=builder)
    built = build_user_text_generator(missing, assignment, slot="primary")  # type: ignore[arg-type]
    assert isinstance(built.generator, NullTextGenerator)
    assert built.provider == "none"
    assert built.model == "assigned-model"

    inactive = SimpleNamespace(
        chat_chain=(_config(row_id=7, enabled=False),),
        builder=builder,
    )
    built = build_user_text_generator(inactive, assignment, slot="primary")  # type: ignore[arg-type]
    assert isinstance(built.generator, NullTextGenerator)
    assert built.provider_config_id == 7
    assert builder.configs == []

    keyless = SimpleNamespace(
        chat_chain=(_config(row_id=7, api_key=None),),
        builder=builder,
    )
    built = build_user_text_generator(keyless, assignment, slot="primary")  # type: ignore[arg-type]
    assert isinstance(built.generator, NullTextGenerator)
    assert builder.configs == []

    active = SimpleNamespace(
        chat_chain=(_config(row_id=7),),
        builder=builder,
    )
    built = build_user_text_generator(active, assignment, slot="primary")  # type: ignore[arg-type]
    assert not isinstance(built.generator, NullTextGenerator)
    assert built.provider == "deepseek"
    assert built.model == "assigned-model"
    assert built.effort == "high"
    assert built.provider_config_id == 7
    assert builder.configs[0].model == "assigned-model"
    assert builder.configs[0].reasoning_effort == "high"

    # The auxiliary slot resolves its own row and keeps its own effort.
    built = build_user_text_generator(active, assignment, slot="auxiliary")  # type: ignore[arg-type]
    assert isinstance(built.generator, NullTextGenerator)
    assert built.provider_config_id == 8


def test_fingerprint_covers_model_effort_and_key_ciphertext() -> None:
    row = _config(row_id=3)
    baseline = assignment_fingerprint(row, "a-model", "low", api_key_ciphertext="c1")
    assert baseline == assignment_fingerprint(
        row, "a-model", "low", api_key_ciphertext="c1"
    )
    assert baseline != assignment_fingerprint(
        row, "a-model", "high", api_key_ciphertext="c1"
    )
    assert baseline != assignment_fingerprint(
        row, "other-model", "low", api_key_ciphertext="c1"
    )
    assert baseline != assignment_fingerprint(
        row, "a-model", "low", api_key_ciphertext="c2"
    )
    moved = row.model_copy(update={"base_url": "https://other.example.com"})
    assert baseline != assignment_fingerprint(
        moved, "a-model", "low", api_key_ciphertext="c1"
    )
