"""Provider outage behavior: bounded automatic retry and safe logging."""

import logging
import time
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.ai.deepseek_client import _http_error
from app.module.agent.protocol.chat_generator_protocol import (
    ChatResult,
    TextDeltaCallback,
)
from app.module.agent.service import agent_service as agent_service_module
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
)
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiProviderError,
)


class TransientChatGenerator(FakeChatGenerator):
    """Fail once before any text, then return the scripted answer."""

    def __init__(self, results: Sequence[ChatResult] | None = None) -> None:
        super().__init__(results)
        self.calls = 0

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        self.calls += 1
        if self.calls == 1:
            raise AiProviderError(
                "HTTP 503: service temporarily unavailable",
                status_code=503,
                retryable=True,
                provider_request_id="req-503",
                provider_error_code="service_unavailable",
            )
        return await super().complete_chat(
            messages,
            tools,
            model=model,
            stream=stream,
            on_text_delta=on_text_delta,
        )


class PartialThenFailChatGenerator(FakeChatGenerator):
    """Emit one visible token, then fail; a retry would duplicate output."""

    def __init__(self) -> None:
        super().__init__([])
        self.calls = 0

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        self.calls += 1
        if on_text_delta is not None:
            await on_text_delta("partial ")
        raise AiProviderError(
            "HTTP 503: service temporarily unavailable",
            status_code=503,
            retryable=True,
            provider_request_id="req-503",
        )


def _new_conversation(client: TestClient) -> int:
    response = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Provider outage"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_transient_provider_failure_retries_before_output(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        agent_service_module,
        "_PROVIDER_RETRY_DELAYS_SECONDS",
        (0.0,),
    )
    caplog.set_level(logging.INFO)
    fake = TransientChatGenerator([text_result("Recovered after the outage.")])
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client)

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Survive a brief provider outage."},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Recovered after the outage."
    assert fake.calls == 2
    assert "provider call retry scheduled" in caplog.text
    assert "status=503" in caplog.text
    assert "attempt=1 max_attempts=2" in caplog.text
    assert "req-503" in caplog.text


def test_transient_provider_failure_after_output_is_not_retried(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_service_module,
        "_PROVIDER_RETRY_DELAYS_SECONDS",
        (0.0,),
    )
    fake = PartialThenFailChatGenerator()
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client)

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Do not duplicate streamed text."},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["status"] == "failed"
    assert body["error_code"] == "provider_error"
    assert body["assistant_entry"]["data"]["finish_reason"] == "error"
    assert fake.calls == 1


def test_provider_http_error_classification_and_safe_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    error = _http_error(
        operation="chat",
        call_id="call-1",
        model="deepseek-flash",
        stream=True,
        status_code=503,
        request_id="req-503",
        body=(
            b'{"error":{"code":"service_unavailable","type":"server_error",'
            b'"message":"service temporarily unavailable","request":"do-not-log-this"}}'
        ),
        started=time.monotonic(),
    )

    assert isinstance(error, AiProviderError)
    assert error.retryable is True
    assert error.status_code == 503
    assert error.provider_request_id == "req-503"
    assert error.provider_error_code == "service_unavailable"
    assert "HTTP 503" in str(error)
    assert "service temporarily unavailable" in str(error)
    assert "status=503" in caplog.text
    assert "retryable=True" in caplog.text
    assert "do-not-log-this" not in caplog.text

    rejected = _http_error(
        operation="chat",
        call_id="call-2",
        model="deepseek-flash",
        stream=False,
        status_code=401,
        request_id="req-401",
        body=b'{"error":{"code":"invalid_api_key","message":"invalid key"}}',
        started=time.monotonic(),
    )
    assert rejected.retryable is False
    assert rejected.status_code == 401

    overflow = _http_error(
        operation="chat",
        call_id="call-3",
        model="deepseek-flash",
        stream=False,
        status_code=400,
        request_id=None,
        body=b'{"error":{"message":"maximum context length is 1000000 tokens"}}',
        started=time.monotonic(),
    )
    assert isinstance(overflow, AiContextWindowError)
