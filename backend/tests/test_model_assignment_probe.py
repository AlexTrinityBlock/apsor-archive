"""Connection probe route: success, failure, timeout, redaction, no writes.

The route always answers HTTP 200 with an outcome (a 404 only for an unknown
endpoint row), never a 500. The probe itself is the real
``ProviderProbe`` fed by a stub factory, so timeout handling, detail clipping,
and key redaction are exercised without a network call.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.infrastructure.ai.probe import ProviderProbe
from app.module.knowledge.domain.provider_runtime_domain import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion
from tests.conftest import UserClient


class _SuccessGenerator:
    async def probe(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 16,
    ) -> AiCompletion:
        del model, reasoning_effort, max_tokens
        return AiCompletion(
            text="OK",
            model="gateway-resolved-model",
            usage={"input_tokens": 4, "output_tokens": 1},
        )


class _RaisingGenerator:
    def __init__(self, message: str) -> None:
        self.message = message

    async def probe(self, **kwargs: Any) -> AiCompletion:
        del kwargs
        raise RuntimeError(self.message)


class _SlowGenerator:
    async def probe(self, **kwargs: Any) -> AiCompletion:
        del kwargs
        await asyncio.sleep(1)
        return AiCompletion(text="OK", model="slow", usage={})


class _StubFactory:
    """Duck-typed provider factory returning one prepared generator."""

    def __init__(self, generator: Any) -> None:
        self.generator = generator
        self.settings = SimpleNamespace(chat_probe_timeout_seconds=20.0)
        self.configs: list[ProviderConfig] = []

    def build_text_generator(self, config: ProviderConfig) -> Any:
        self.configs.append(config)
        return self.generator


def _install_probe(
    client: TestClient,
    generator: Any,
    *,
    timeout_seconds: float = 20.0,
) -> _StubFactory:
    factory = _StubFactory(generator)
    client.app.state.provider_probe = ProviderProbe(
        factory,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,
    )
    return factory


def _create_chat_row(
    client: TestClient,
    *,
    label: str,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    api_key: str | None = "sk-probe-row-key-1234",
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


def _assignment_snapshot(engine: Engine, user_id: int) -> tuple[Any, ...]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(
                    "SELECT chat_provider_config_id, chat_model, chat_reasoning_effort, "
                    "aux_provider_config_id, aux_model, aux_reasoning_effort, "
                    "chat_context_window_tokens, chat_compaction_threshold_tokens, "
                    "updated_at FROM app_user WHERE id = :user_id"
                ),
                {"user_id": user_id},
            ).one()
        )


def test_probe_success_reports_the_gateway_model_and_writes_nothing(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    row_id = _create_chat_row(client, label="probe row")
    factory = _install_probe(client, _SuccessGenerator())
    before = _assignment_snapshot(owner_engine, root_account.user_id)

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={
            "model": "deepseek-flash",
            "reasoning_effort": "high",
            "purpose": "primary",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["resolved_model"] == "gateway-resolved-model"
    assert body["usage"] == {"input_tokens": 4, "output_tokens": 1}
    assert body["detail"] is None
    assert isinstance(body["latency_ms"], int)
    assert len(factory.configs) == 1
    assert factory.configs[0].model == "deepseek-flash"
    assert factory.configs[0].reasoning_effort == "high"
    assert _assignment_snapshot(owner_engine, root_account.user_id) == before


def test_probe_failure_is_http_200_with_ok_false(client: TestClient) -> None:
    row_id = _create_chat_row(client, label="probe row")
    _install_probe(client, _RaisingGenerator("model not available"))

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "missing-model", "reasoning_effort": "low"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["resolved_model"] is None
    assert body["detail"] == "model not available"


def test_probe_timeout_is_http_200_with_ok_false(client: TestClient) -> None:
    row_id = _create_chat_row(client, label="probe row")
    _install_probe(client, _SlowGenerator(), timeout_seconds=0.01)

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "deepseek-flash", "reasoning_effort": "low"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["detail"] == "probe timed out"


def test_probe_failure_redacts_the_endpoint_key(client: TestClient) -> None:
    secret = "sk-probe-secret-9876"
    row_id = _create_chat_row(client, label="probe row", api_key=secret)
    _install_probe(
        client,
        _RaisingGenerator(f"the provider rejected API key {secret}"),
    )

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "deepseek-flash", "reasoning_effort": "low"},
    )
    assert response.status_code == 200, response.text
    assert secret not in response.text
    body = response.json()
    assert body["ok"] is False
    assert "[redacted]" in body["detail"]


def test_probe_of_an_inactive_row_returns_ok_false_without_calling_out(
    client: TestClient,
) -> None:
    row_id = _create_chat_row(client, label="inactive row", activate=False)
    factory = _install_probe(client, _SuccessGenerator())

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "deepseek-flash", "reasoning_effort": "low"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["detail"] == "the endpoint is not active."
    assert factory.configs == []


def test_probe_of_a_keyless_row_returns_ok_false(client: TestClient) -> None:
    row_id = _create_chat_row(
        client,
        label="keyless row",
        provider="openai-compatible",
        model="local-model",
        api_key=None,
    )
    factory = _install_probe(client, _SuccessGenerator())

    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "local-model"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["detail"] == "the endpoint has no API key."
    assert factory.configs == []


def test_probe_of_an_unknown_row_is_404(client: TestClient) -> None:
    _install_probe(client, _SuccessGenerator())
    response = client.post(
        "/api/v1/chat-endpoints/999999/probe",
        json={"model": "deepseek-flash", "reasoning_effort": "low"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "provider_not_found"


def test_auxiliary_probe_requires_an_effort(client: TestClient) -> None:
    row_id = _create_chat_row(client, label="probe row")
    _install_probe(client, _SuccessGenerator())
    response = client.post(
        f"/api/v1/chat-endpoints/{row_id}/probe",
        json={"model": "deepseek-flash", "purpose": "auxiliary"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"
