"""Offline contract tests for the native Anthropic Messages adapter.

Every request goes through ``httpx.MockTransport``; no test opens a socket. The
cases cover request translation, the named-event SSE parser, usage buckets,
effort placement, error mapping, and the vision extractor wrapper.
"""

import asyncio
import base64
import json
from collections.abc import Callable
from typing import Any, Literal

import httpx
import pytest

from app.infrastructure.ai import anthropic_client
from app.infrastructure.ai.anthropic_client import AnthropicClient, _messages_url
from app.infrastructure.ai.anthropic_vision import (
    VISION_DOCUMENT_MAX_TOKENS,
    VISION_DOCUMENT_USER_PROMPT,
    VISION_IMAGE_MAX_TOKENS,
    VISION_IMAGE_USER_PROMPT,
    AnthropicVisionExtractor,
)
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiProviderError,
    VisionExtractionError,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route the client's per-call AsyncClient through a MockTransport."""
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        del args
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(anthropic_client.httpx, "AsyncClient", factory)


def _make_client(**overrides: Any) -> AnthropicClient:
    options: dict[str, Any] = {
        "api_key": "test-key",
        "base_url": "https://api.anthropic.com",
        "model": "claude-haiku-5-5",
        "timeout_seconds": 5.0,
        "max_tokens": 2000,
        "chat_max_tokens": 64000,
    }
    options.update(overrides)
    return AnthropicClient(**options)


def _request_json(request: httpx.Request) -> dict[str, Any]:
    parsed = json.loads(request.content)
    assert isinstance(parsed, dict)
    return parsed


def _message_body(
    content: list[dict[str, Any]],
    *,
    stop_reason: str = "end_turn",
    usage: dict[str, Any] | None = None,
    model: str = "claude-haiku-5-5",
) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage
        or {
            "input_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 4,
        },
    }


def _sse(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(
        f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events
    )


def _streaming_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=text,
    )


# ---------------------------------------------------------------------------
# Non-streaming requests
# ---------------------------------------------------------------------------


def test_complete_text_non_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_message_body([{"type": "text", "text": "Hello there"}]),
        )

    _install_transport(monkeypatch, handler)
    client = _make_client()

    completion = asyncio.run(client.complete_text("System prompt", "Hello"))

    assert completion.text == "Hello there"
    assert completion.model == "claude-haiku-5-5"
    assert completion.usage == {
        "input_tokens": 10,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
        "prompt_cache_hit_tokens": 0,
        "cached_tokens": 0,
    }
    assert str(calls[0].url) == "https://api.anthropic.com/v1/messages"
    assert calls[0].headers["x-api-key"] == "test-key"
    assert calls[0].headers["anthropic-version"] == "2026-10-21"
    assert calls[0].headers["content-type"] == "application/json"
    payload = _request_json(calls[0])
    assert payload["model"] == "claude-haiku-5-5"
    assert payload["max_tokens"] == 2000
    assert payload["stream"] is False
    assert payload["system"] == "System prompt"
    assert payload["messages"] == [{"role": "user", "content": "Hello"}]
    for key in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
        assert key not in payload


def test_complete_chat_non_streaming_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_message_body(
                [
                    {"type": "text", "text": "Searching."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "search_knowledge",
                        "input": {"query": "cats"},
                    },
                ],
                stop_reason="tool_use",
                usage={
                    "input_tokens": 30,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 7,
                    "output_tokens": 9,
                },
            ),
        )

    _install_transport(monkeypatch, handler)
    client = _make_client()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search the archive",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]

    result = asyncio.run(
        client.complete_chat(
            [
                {"role": "system", "content": "Frozen prompt"},
                {"role": "user", "content": "Find cats"},
            ],
            tools,
        )
    )

    assert result.text == "Searching."
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.call_id == "toolu_1"
    assert call.name == "search_knowledge"
    assert call.arguments == {"query": "cats"}
    assert call.parse_error is None
    assert result.usage["prompt_tokens"] == 42
    assert result.usage["completion_tokens"] == 9
    payload = _request_json(calls[0])
    assert payload["max_tokens"] == 64000
    assert payload["tools"] == [
        {
            "name": "search_knowledge",
            "description": "Search the archive",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert "tool_choice" not in payload


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_complete_chat_streaming_named_events(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-haiku-5-5",
                    "usage": {
                        "input_tokens": 10,
                        "cache_creation_input_tokens": 2,
                        "cache_read_input_tokens": 3,
                        "output_tokens": 0,
                    },
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        ("ping", {"type": "ping"}),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hel"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "lo"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_9",
                    "name": "search_knowledge",
                    "input": {},
                },
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"query":'},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '"cats"}'},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        # No [DONE] sentinel: Anthropic terminates at message_stop.
        return _streaming_response(_sse(events))

    _install_transport(monkeypatch, handler)
    client = _make_client()
    deltas: list[str] = []

    async def collect(piece: str) -> None:
        deltas.append(piece)

    result = asyncio.run(
        client.complete_chat(
            [
                {"role": "system", "content": "Frozen prompt"},
                {"role": "user", "content": "Find cats"},
            ],
            [],
            stream=True,
            on_text_delta=collect,
        )
    )

    assert deltas == ["Hel", "lo"]
    assert result.text == "Hello"
    assert result.finish_reason == "tool_calls"
    assert result.model == "claude-haiku-5-5"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "toolu_9"
    assert result.tool_calls[0].arguments == {"query": "cats"}
    assert result.usage == {
        "input_tokens": 10,
        "cache_creation_input_tokens": 2,
        "cache_read_input_tokens": 3,
        "prompt_tokens": 15,
        "completion_tokens": 5,
        "total_tokens": 20,
        "prompt_cache_hit_tokens": 3,
        "cached_tokens": 3,
    }
    payload = _request_json(calls[0])
    assert payload["stream"] is True


def test_text_callback_forces_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-haiku-5-5",
                    "usage": {"input_tokens": 2, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "OK"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _streaming_response(_sse(events))

    _install_transport(monkeypatch, handler)
    deltas: list[str] = []

    async def collect(piece: str) -> None:
        deltas.append(piece)

    result = asyncio.run(
        _make_client().complete_chat(
            [{"role": "user", "content": "Question"}],
            [],
            stream=False,
            on_text_delta=collect,
        )
    )

    assert deltas == ["OK"]
    assert result.text == "OK"
    assert _request_json(calls[0])["stream"] is True


# ---------------------------------------------------------------------------
# Usage, system hoisting, effort
# ---------------------------------------------------------------------------


def test_usage_buckets_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_message_body(
                [{"type": "text", "text": "Done"}],
                usage={
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 20,
                    "cache_read_input_tokens": 30,
                    "output_tokens": 40,
                },
            ),
        )

    _install_transport(monkeypatch, handler)
    completion = asyncio.run(_make_client().complete_text("System", "User"))

    assert completion.usage == {
        "input_tokens": 100,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 30,
        "prompt_tokens": 150,
        "completion_tokens": 40,
        "total_tokens": 190,
        "prompt_cache_hit_tokens": 30,
        "cached_tokens": 30,
    }


def test_system_messages_are_hoisted_and_sampling_controls_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    client = _make_client()

    asyncio.run(
        client.complete_chat(
            [
                {"role": "system", "content": "Frozen prompt"},
                {"role": "user", "content": "Question"},
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "Agent status block"}],
                },
            ],
            [],
        )
    )

    payload = _request_json(calls[0])
    assert payload["system"] == [
        {"type": "text", "text": "Frozen prompt\n\nAgent status block"}
    ]
    assert [message["role"] for message in payload["messages"]] == ["user"]
    for key in ("temperature", "top_p", "top_k"):
        assert key not in payload
    assert "output_config" not in payload
    assert "cache_control" not in payload["system"][0]
    assert "tools" not in payload


@pytest.mark.parametrize(
    ("effort", "expected"),
    [
        ("low", {"effort": "low"}),
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_output_config_effort_only_when_non_empty(
    monkeypatch: pytest.MonkeyPatch,
    effort: str | None,
    expected: dict[str, str] | None,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    client = _make_client(reasoning_effort=effort)

    asyncio.run(client.complete_text("System", "User"))

    payload = _request_json(calls[0])
    assert payload.get("output_config") == expected


def test_complete_chat_sends_output_config_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    client = _make_client(reasoning_effort="medium")

    asyncio.run(
        client.complete_chat([{"role": "user", "content": "Question"}], [])
    )

    payload = _request_json(calls[0])
    assert payload["output_config"] == {"effort": "medium"}
    assert payload["max_tokens"] == 64000


def test_probe_uses_candidate_model_effort_and_small_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    client = _make_client(reasoning_effort="low")

    completion = asyncio.run(
        client.probe(
            model="claude-sonnet-5-5",
            reasoning_effort="high",
            max_tokens=16,
        )
    )

    assert completion.text == "OK"
    payload = _request_json(calls[0])
    assert payload["model"] == "claude-sonnet-5-5"
    assert payload["max_tokens"] == 16
    assert payload["output_config"] == {"effort": "high"}
    assert payload["system"] == "You are a connection test."
    assert payload["messages"] == [
        {"role": "user", "content": "Reply with the single word OK."}
    ]


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error_type", "retryable"),
    [
        (400, "invalid_request_error", False),
        (401, "authentication_error", False),
        (403, "permission_error", False),
        (404, "not_found_error", False),
        (429, "rate_limit_error", True),
        (500, "api_error", True),
        (529, "overloaded_error", True),
    ],
)
def test_http_error_rows(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    error_type: str,
    retryable: bool,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "type": "error",
                "error": {"type": error_type, "message": "provider says no"},
            },
            headers={"request-id": "req_abc"},
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(_make_client().complete_text("System", "User"))

    assert not isinstance(info.value, AiContextWindowError)
    assert info.value.status_code == status
    assert info.value.retryable is retryable
    assert info.value.provider_request_id == "req_abc"
    assert info.value.provider_error_code == error_type
    assert info.value.provider_error_type == error_type
    assert info.value.provider_error_message == "provider says no"


def test_request_too_large_is_a_context_window_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413,
            json={
                "type": "error",
                "error": {"type": "request_too_large", "message": "request too large"},
            },
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiContextWindowError):
        asyncio.run(_make_client().complete_text("System", "User"))


@pytest.mark.parametrize(
    "message",
    [
        "prompt is too long: 250000 tokens > 200000 maximum",
        "input length and max_tokens exceed context limit",
    ],
)
def test_context_markers_map_to_context_window(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": message},
            },
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiContextWindowError):
        asyncio.run(_make_client().complete_text("System", "User"))


def test_provider_error_message_is_clipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "x" * 800},
            },
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(_make_client().complete_text("System", "User"))

    assert len(info.value.provider_error_message or "") == 300


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("connection refused"), httpx.ReadTimeout("timed out")],
)
def test_transport_errors_are_retryable(
    monkeypatch: pytest.MonkeyPatch,
    error: httpx.HTTPError,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise error

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(_make_client().complete_text("System", "User"))

    assert info.value.retryable is True
    assert info.value.status_code is None


def test_stream_error_event_maps_to_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-haiku-5-5",
                    "usage": {"input_tokens": 3, "output_tokens": 0},
                },
            },
        ),
        (
            "error",
            {
                "type": "error",
                "error": {"type": "overloaded_error", "message": "try later"},
                "request_id": "req_stream",
            },
        ),
    ]
    _install_transport(
        monkeypatch,
        lambda _request: _streaming_response(_sse(events)),
    )

    with pytest.raises(AiProviderError) as info:
        asyncio.run(
            _make_client().complete_chat([{"role": "user", "content": "Hi"}], [], stream=True)
        )

    assert info.value.retryable is True
    assert info.value.provider_error_code == "overloaded_error"
    assert info.value.provider_request_id == "req_stream"


# ---------------------------------------------------------------------------
# Truncated and empty streams
# ---------------------------------------------------------------------------


def test_missing_message_stop_is_a_retryable_truncated_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-haiku-5-5",
                    "usage": {"input_tokens": 3, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "partial"},
            },
        ),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 1},
            },
        ),
    ]
    _install_transport(
        monkeypatch,
        lambda _request: _streaming_response(_sse(events)),
    )

    with pytest.raises(AiProviderError) as info:
        asyncio.run(
            _make_client().complete_chat([{"role": "user", "content": "Hi"}], [], stream=True)
        )

    assert info.value.retryable is True
    assert "truncated stream" in str(info.value)


def test_empty_non_streaming_completion_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_message_body([], stop_reason="end_turn"))

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(_make_client().complete_chat([{"role": "user", "content": "Hi"}], []))

    assert info.value.retryable is True
    assert "empty completion" in str(info.value)


def test_empty_streaming_completion_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stream",
                    "model": "claude-haiku-5-5",
                    "usage": {"input_tokens": 3, "output_tokens": 0},
                },
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    _install_transport(
        monkeypatch,
        lambda _request: _streaming_response(_sse(events)),
    )

    with pytest.raises(AiProviderError) as info:
        asyncio.run(
            _make_client().complete_chat([{"role": "user", "content": "Hi"}], [], stream=True)
        )

    assert info.value.retryable is True
    assert "empty completion" in str(info.value)


# ---------------------------------------------------------------------------
# Base URL shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.anthropic.com", "https://api.anthropic.com/v1/messages"),
        ("https://api.anthropic.com/", "https://api.anthropic.com/v1/messages"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com/v1/messages"),
        ("https://api.anthropic.com/v1/", "https://api.anthropic.com/v1/messages"),
        (
            "https://api.anthropic.com/v1/messages",
            "https://api.anthropic.com/v1/messages",
        ),
        (
            "https://api.deepseek.com/anthropic",
            "https://api.deepseek.com/anthropic/v1/messages",
        ),
        (
            "https://gateway.example.com/anthropic/",
            "https://gateway.example.com/anthropic/v1/messages",
        ),
    ],
)
def test_messages_url_resolution(base_url: str, expected: str) -> None:
    assert _messages_url(base_url) == expected


def test_deepseek_compatible_base_url_is_used_on_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    client = _make_client(base_url="https://api.deepseek.com/anthropic")

    asyncio.run(client.complete_text("System", "User"))

    assert str(calls[0].url) == "https://api.deepseek.com/anthropic/v1/messages"


# ---------------------------------------------------------------------------
# Message and tool translation
# ---------------------------------------------------------------------------


def test_messages_images_and_tool_results_are_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_message_body([{"type": "text", "text": "OK"}]))

    _install_transport(monkeypatch, handler)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "Search the archive",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                "extra": "dropped",
            },
        }
    ]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "Frozen prompt"},
        {"role": "user", "content": "look"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge",
                        "arguments": '{"query":"cats"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "content": "result one"},
        {"role": "tool", "tool_call_id": "toolu_2", "content": "result two"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "and this"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,QUJD"},
                },
            ],
        },
    ]

    asyncio.run(_make_client().complete_chat(messages, tools))

    payload = _request_json(calls[0])
    assert payload["system"] == [
        {
            "type": "text",
            "text": "Frozen prompt",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    translated = payload["messages"]
    assert [message["role"] for message in translated] == [
        "user",
        "assistant",
        "user",
    ]
    assert translated[0]["content"] == [{"type": "text", "text": "look"}]
    assert translated[1]["content"] == [
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "search_knowledge",
            "input": {"query": "cats"},
        }
    ]
    assert translated[2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": "result one",
        },
        {
            "type": "tool_result",
            "tool_use_id": "toolu_2",
            "content": "result two",
        },
        {"type": "text", "text": "and this"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "QUJD",
            },
            "cache_control": {"type": "ephemeral"},
        },
    ]
    assert payload["tools"] == [
        {
            "name": "search_knowledge",
            "description": "Search the archive",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert "tool_choice" not in payload


def test_assistant_prefill_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent for a prefill transcript")

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(
            _make_client().complete_chat(
                [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "prefill"},
                ],
                [],
            )
        )

    assert info.value.retryable is False
    assert "prefill" in str(info.value)


# ---------------------------------------------------------------------------
# JSON mode
# ---------------------------------------------------------------------------


def test_complete_json_adds_the_json_instruction_and_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_message_body([{"type": "text", "text": '{"answer": 42}'}]),
        )

    _install_transport(monkeypatch, handler)

    completion = asyncio.run(_make_client().complete_json("Extract facts", "Text"))

    assert completion.text == '{"answer": 42}'
    payload = _request_json(calls[0])
    system_text = payload["system"]
    assert system_text.startswith("Extract facts")
    assert "Return only one valid JSON object" in system_text


def test_complete_json_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_message_body([{"type": "text", "text": "not json"}]),
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(AiProviderError) as info:
        asyncio.run(_make_client().complete_json("Extract facts", "Text"))

    assert info.value.retryable is False
    assert "invalid JSON completion" in str(info.value)


# ---------------------------------------------------------------------------
# Vision extractor
# ---------------------------------------------------------------------------


def _vision_json() -> dict[str, Any]:
    return {
        "text": "Invoice text",
        "tables": ["| a | b |\n| - | - |\n| 1 | 2 |"],
        "description": "A receipt on a desk.",
        "caption": "Receipt",
        "title": "Receipt 42",
        "summary": "A receipt for two items.",
        "document_type": "receipt",
        "tags": [
            "receipt",
            "invoice",
            "tax",
            "total",
            "store",
            "date",
            "amount",
            "item",
            "extra",
        ],
        "language": "en",
    }


@pytest.mark.parametrize(
    ("mode", "max_tokens", "user_prompt"),
    [
        ("image", VISION_IMAGE_MAX_TOKENS, VISION_IMAGE_USER_PROMPT),
        ("document", VISION_DOCUMENT_MAX_TOKENS, VISION_DOCUMENT_USER_PROMPT),
    ],
)
def test_vision_extractor_sends_one_image_block(
    monkeypatch: pytest.MonkeyPatch,
    mode: Literal["image", "document"],
    max_tokens: int,
    user_prompt: str,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_message_body(
                [{"type": "text", "text": json.dumps(_vision_json())}],
                usage={
                    "input_tokens": 1200,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 300,
                },
            ),
        )

    _install_transport(monkeypatch, handler)
    extractor = AnthropicVisionExtractor(
        api_key="test-key",
        base_url="https://api.anthropic.com",
        model="claude-haiku-5-5",
        timeout_seconds=5.0,
        reasoning_effort="low",
    )
    image_bytes = b"fake-image-bytes"

    document = asyncio.run(
        extractor.extract(
            image_bytes,
            "image/png",
            system_prompt="Rendered vision prompt",
            mode=mode,
        )
    )

    assert isinstance(document, VisionDocument)
    assert document.text == "Invoice text"
    assert document.ocr_text == "Invoice text"
    assert document.caption == "Receipt"
    assert document.title == "Receipt 42"
    assert document.document_type == "receipt"
    assert len(document.tags) == 8
    assert "extra" not in document.tags
    assert document.tables == ["| a | b |\n| - | - |\n| 1 | 2 |"]
    assert document.description == "A receipt on a desk."
    assert document.usage["prompt_tokens"] == 1200
    assert document.usage["completion_tokens"] == 300

    payload = _request_json(calls[0])
    assert payload["max_tokens"] == max_tokens
    assert payload["output_config"] == {"effort": "low"}
    assert payload["system"] == [{"type": "text", "text": "Rendered vision prompt"}]
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": user_prompt}
    assert content[1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }
    assert len([part for part in content if part["type"] == "image"]) == 1
    assert extractor.model_name == "claude-haiku-5-5"


def test_vision_extractor_wraps_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "image is not supported",
                },
            },
        )

    _install_transport(monkeypatch, handler)
    extractor = AnthropicVisionExtractor(
        api_key="test-key",
        base_url="https://api.anthropic.com",
        model="claude-haiku-5-5",
        timeout_seconds=5.0,
    )

    with pytest.raises(VisionExtractionError) as info:
        asyncio.run(
            extractor.extract(b"image", "image/png", system_prompt="Prompt")
        )

    assert "Vision extraction failed" in str(info.value)
