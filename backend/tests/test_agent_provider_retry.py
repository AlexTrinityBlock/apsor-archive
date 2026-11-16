"""Provider outage behavior: bounded automatic retry and safe logging."""

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.ai import deepseek_client as deepseek_client_module
from app.infrastructure.ai.deepseek_client import (
    DeepSeekClient,
    _http_error,
    _parse_arguments,
)
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


class _FakeResponse:
    """Minimal httpx non-streaming response for one scripted reply."""

    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = {}
        self.content = json.dumps(payload).encode("utf-8")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeStreamResponse:
    """Minimal streaming response; errors expose a body, success yields SSE lines."""

    def __init__(
        self,
        status_code: int,
        body: bytes,
        *,
        lines: Sequence[str] = (),
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status_code
        self._body = body
        self._lines = lines
        self.headers = {"content-type": content_type}

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self) -> Any:
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeAsyncClient:
    """Return scripted responses and record every JSON payload sent."""

    def __init__(
        self,
        responses: list[_FakeResponse | _FakeStreamResponse],
        requests: list[dict[str, Any]],
    ) -> None:
        self._responses = responses
        self._requests = requests

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeResponse:
        del url, headers
        self._requests.append(dict(json))
        response = self._responses.pop(0)
        assert isinstance(response, _FakeResponse)
        return response

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeStreamContext:
        del method, url, headers
        self._requests.append(dict(json))
        response = self._responses.pop(0)
        assert isinstance(response, _FakeStreamResponse)
        return _FakeStreamContext(response)


def _chat_client(*, chat_max_tokens: int) -> DeepSeekClient:
    return DeepSeekClient(
        api_key="secret-api-key",
        base_url="https://example.invalid",
        model="deepseek-flash",
        timeout_seconds=1.0,
        max_tokens=1_800,
        chat_max_tokens=chat_max_tokens,
        temperature=0.0,
        supports_thinking=False,
    )


def _chat_completion(text: str) -> dict[str, Any]:
    return {
        "model": "deepseek-flash",
        "choices": [
            {
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_FakeResponse | _FakeStreamResponse],
    requests: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        deepseek_client_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(responses, requests),
    )


def test_chat_400_max_tokens_retries_once_without_the_cap(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A provider cap rejection drops max_tokens and is remembered."""
    caplog.set_level(logging.WARNING)
    requests: list[dict[str, Any]] = []
    responses: list[_FakeResponse | _FakeStreamResponse] = [
        _FakeResponse(
            400,
            {"error": {"message": "max_tokens must be less than 8192"}},
        ),
        _FakeResponse(200, _chat_completion("First answer.")),
        _FakeResponse(200, _chat_completion("Second answer.")),
    ]
    _install_fake_client(monkeypatch, responses, requests)
    client = _chat_client(chat_max_tokens=20_000)

    first = asyncio.run(
        client.complete_chat([{"role": "user", "content": "First"}], [])
    )
    assert first.text == "First answer."
    assert "max_tokens" in requests[0]
    assert "max_tokens" not in requests[1]
    assert client.max_output_tokens == 0

    second = asyncio.run(
        client.complete_chat([{"role": "user", "content": "Second"}], [])
    )
    assert second.text == "Second answer."
    assert len(requests) == 3
    assert "max_tokens" not in requests[2]

    assert caplog.text.count("provider rejected chat max_tokens") == 1
    assert "secret-api-key" not in caplog.text
    assert "less than 8192" not in caplog.text


def test_streaming_chat_400_max_tokens_retries_once_without_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The streaming path applies the same one-shot cap fallback."""
    requests: list[dict[str, Any]] = []
    success_lines = (
        'data: {"model":"deepseek-flash","choices":[{"delta":{"content":"ok"},'
        '"finish_reason":"stop"}]}',
        "data: [DONE]",
    )
    responses: list[_FakeResponse | _FakeStreamResponse] = [
        _FakeStreamResponse(
            400,
            b'{"error":{"message":"max_tokens exceeds the model limit"}}',
        ),
        _FakeStreamResponse(
            200,
            b"",
            lines=success_lines,
            content_type="text/event-stream",
        ),
    ]
    _install_fake_client(monkeypatch, responses, requests)
    client = _chat_client(chat_max_tokens=20_000)

    result = asyncio.run(
        client.complete_chat(
            [{"role": "user", "content": "Stream this"}],
            [],
            stream=True,
        )
    )

    assert result.text == "ok"
    assert "max_tokens" in requests[0]
    assert "max_tokens" not in requests[1]
    assert client.max_output_tokens == 0


def test_other_400_responses_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a body that names max_tokens triggers the fallback."""
    requests: list[dict[str, Any]] = []
    responses: list[_FakeResponse | _FakeStreamResponse] = [
        _FakeResponse(400, {"error": {"message": "invalid request format"}}),
    ]
    _install_fake_client(monkeypatch, responses, requests)
    client = _chat_client(chat_max_tokens=20_000)

    with pytest.raises(AiProviderError) as raised:
        asyncio.run(
            client.complete_chat([{"role": "user", "content": "Fail"}], [])
        )

    assert raised.value.status_code == 400
    assert len(requests) == 1
    assert "max_tokens" in requests[0]
    assert client.max_output_tokens == 20_000


def test_tool_arguments_accept_only_trailing_closing_brackets() -> None:
    """A complete object plus extra closing brackets parses; junk does not."""
    obj = {"title": "3D sphere", "figure": {"data": [{"type": "surface"}]}}
    raw = json.dumps(obj, separators=(",", ":"))
    accepted = {
        "one brace": "}",
        "five braces": "}}}}}",
        "bracket": "]",
        "mixed whitespace": " \n}\n] ",
    }
    for label, suffix in accepted.items():
        parsed, error = _parse_arguments(raw + suffix)
        assert error is None, label
        assert parsed == obj, label

    rejected = {
        "trailing words": '{"title":"sphere"} trailing',
        "truncated object": '{"title":"sphere"',
        "non-object prefix": '"sphere"}}',
    }
    for label, value in rejected.items():
        parsed, error = _parse_arguments(value)
        assert parsed == {}, label
        assert error == "Tool arguments are not valid JSON.", label
