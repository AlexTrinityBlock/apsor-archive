"""Offline tests for the chat endpoint connection probe.

Every provider call goes through ``httpx.MockTransport`` or a deterministic
stub client. No test opens a socket, touches a database, or reads a real key.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.infrastructure.ai import anthropic_client, deepseek_client
from app.infrastructure.ai.probe import ProbeOutcome, ProviderProbe
from app.infrastructure.ai.provider_factory import ProviderFactory
from app.infrastructure.config.settings import Settings
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route one client module's per-call AsyncClient through MockTransport."""
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        del args
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


def _config(
    provider: str,
    *,
    model: str,
    base_url: str | None,
    key: str,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        capability="chat",
        provider=provider,
        label=provider,
        model=model,
        base_url=base_url,
        api_key=key,
        dimension=None,
        enabled=True,
        source="database",
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
    )


def _request_json(request: httpx.Request) -> dict[str, Any]:
    parsed = json.loads(request.content)
    assert isinstance(parsed, dict)
    return parsed


class _StubFactory:
    """A factory duck type that returns one prepared client."""

    def __init__(self, client: Any, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.configs: list[ProviderConfig] = []

    def build_text_generator(self, config: ProviderConfig) -> Any:
        self.configs.append(config)
        return self.client


class _RaisingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def probe(self, **kwargs: Any) -> AiCompletion:
        del kwargs
        raise self.error


class _SlowClient:
    async def probe(self, **kwargs: Any) -> AiCompletion:
        del kwargs
        await asyncio.sleep(0.2)
        return AiCompletion(text="OK", model="slow-model", usage={})


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_probe_success_uses_the_candidate_anthropic_model_and_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "msg_probe",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 10,
                    "cache_creation_input_tokens": 1,
                    "cache_read_input_tokens": 2,
                    "output_tokens": 3,
                },
            },
        )

    _install_transport(monkeypatch, anthropic_client, handler)
    factory = ProviderFactory(
        Settings(anthropic_api_key="sk-ant-probe-1234", anthropic_timeout_seconds=5.0)
    )
    config = _config(
        "anthropic",
        model="claude-sonnet-5-5",
        base_url="https://api.anthropic.com",
        key="sk-ant-probe-1234",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(
            config,
            model="claude-haiku-5-5",
            reasoning_effort="low",
        )
    )

    assert isinstance(outcome, ProbeOutcome)
    assert outcome.ok is True
    assert outcome.detail is None
    assert outcome.latency_ms >= 0
    assert outcome.resolved_model == "claude-haiku-5-5"
    assert outcome.usage["prompt_tokens"] == 13
    assert outcome.usage["completion_tokens"] == 3
    assert outcome.usage["cache_creation_input_tokens"] == 1

    body = _request_json(calls[0])
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 16
    assert body["stream"] is False
    assert body["output_config"] == {"effort": "low"}
    assert str(calls[0].url) == "https://api.anthropic.com/v1/messages"


def test_probe_success_sends_deepseek_effort_without_the_legacy_thinking_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-reasoner",
                "choices": [
                    {
                        "message": {"content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 1,
                    "total_tokens": 8,
                },
            },
        )

    _install_transport(monkeypatch, deepseek_client, handler)
    factory = ProviderFactory(
        Settings(deepseek_api_key="ds-probe-key-1234", deepseek_timeout_seconds=5.0)
    )
    config = _config(
        "deepseek",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        key="ds-probe-key-1234",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(
            config,
            model="deepseek-reasoner",
            reasoning_effort="high",
        )
    )

    assert outcome.ok is True
    assert outcome.resolved_model == "deepseek-reasoner"
    assert outcome.usage["prompt_tokens"] == 7
    assert outcome.usage["total_tokens"] == 8

    body = _request_json(calls[0])
    assert body["model"] == "deepseek-reasoner"
    assert body["max_tokens"] == 16
    assert body["stream"] is False
    assert body["reasoning_effort"] == "high"
    assert "thinking" not in body


def test_probe_without_effort_keeps_the_deepseek_thinking_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 1},
            },
        )

    _install_transport(monkeypatch, deepseek_client, handler)
    factory = ProviderFactory(Settings(deepseek_api_key="ds-probe-key-5678"))
    config = _config(
        "deepseek",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        key="ds-probe-key-5678",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(config, model="deepseek-flash", reasoning_effort=None)
    )

    assert outcome.ok is True
    body = _request_json(calls[0])
    assert "reasoning_effort" not in body
    assert body["thinking"] == {"type": "disabled"}


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_probe_maps_a_provider_error_to_a_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": "invalid_api_key",
                    "type": "authentication_error",
                    "message": "Incorrect API key provided.",
                }
            },
        )

    _install_transport(monkeypatch, deepseek_client, handler)
    factory = ProviderFactory(Settings(deepseek_api_key="ds-probe-key-9999"))
    config = _config(
        "deepseek",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        key="ds-probe-key-9999",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(
            config,
            model="deepseek-flash",
            reasoning_effort="low",
        )
    )

    assert outcome.ok is False
    assert outcome.resolved_model is None
    assert outcome.usage == {}
    assert outcome.detail is not None
    assert "401" in outcome.detail
    assert "Incorrect API key" in outcome.detail
    assert "ds-probe-key-9999" not in outcome.detail
    assert len(outcome.detail) <= 300


def test_probe_timeout_uses_the_settings_value() -> None:
    settings = Settings(_env_file=None, chat_probe_timeout_seconds=0.01)
    factory = _StubFactory(_SlowClient(), settings)
    config = _config(
        "anthropic",
        model="claude-haiku-5-5",
        base_url="https://api.anthropic.com",
        key="sk-ant-timeout-1234",
    )

    probe = ProviderProbe(factory)  # type: ignore[arg-type]
    assert probe.timeout_seconds == 0.01
    outcome = asyncio.run(
        probe.probe(config, model="claude-haiku-5-5", reasoning_effort="low")
    )

    assert outcome.ok is False
    assert outcome.detail == "probe timed out"
    assert outcome.latency_ms >= 0
    # The candidate config was still built through the factory.
    assert factory.configs[0].model == "claude-haiku-5-5"
    assert factory.configs[0].reasoning_effort == "low"


def test_probe_rejects_an_unknown_provider_without_a_network_call() -> None:
    settings = Settings(deepseek_api_key="ds-probe-key-1234")
    factory = ProviderFactory(settings)
    config = _config(
        "mystery-provider",
        model="some-model",
        base_url=None,
        key="sk-unknown-1234",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(
            config,
            model="some-model",
            reasoning_effort=None,
        )
    )

    assert outcome.ok is False
    assert outcome.detail is not None
    assert "provider not configured" in outcome.detail


def test_probe_never_logs_or_returns_the_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "sk-secret-probe-key-1234"
    settings = Settings(_env_file=None)
    factory = _StubFactory(_RaisingClient(RuntimeError(f"upstream echoed {key}")), settings)
    config = _config(
        "anthropic",
        model="claude-haiku-5-5",
        base_url="https://api.anthropic.com",
        key=key,
    )

    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(
            ProviderProbe(factory).probe(  # type: ignore[arg-type]
                config,
                model="claude-haiku-5-5",
                reasoning_effort="low",
            )
        )

    assert outcome.ok is False
    assert outcome.detail is not None
    assert key not in outcome.detail
    assert "[redacted]" in outcome.detail
    assert key not in caplog.text
    # Only the provider, model, and exception type may be logged.
    assert "error_type=RuntimeError" in caplog.text


def test_probe_clips_an_oversized_failure_detail() -> None:
    settings = Settings(_env_file=None)
    factory = _StubFactory(_RaisingClient(RuntimeError("x" * 1_000)), settings)
    config = _config(
        "anthropic",
        model="claude-haiku-5-5",
        base_url="https://api.anthropic.com",
        key="sk-ant-long-1234",
    )

    outcome = asyncio.run(
        ProviderProbe(factory).probe(  # type: ignore[arg-type]
            config,
            model="claude-haiku-5-5",
            reasoning_effort=None,
        )
    )

    assert outcome.ok is False
    assert outcome.detail is not None
    assert len(outcome.detail) == 300
