"""Provider reasoning capture, its UI/transcript projection, and SSE ordering.

The provider tests use ``httpx.MockTransport`` only. The agent tests drive the
real turn loop through ``FakeChatGenerator``; no live provider is contacted.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.infrastructure.ai import anthropic_client, deepseek_client
from app.infrastructure.ai.anthropic_client import AnthropicClient
from app.infrastructure.ai.deepseek_client import DeepSeekClient
from app.module.agent.domain.agent_domain import MAX_ASSISTANT_REASONING_CHARS
from app.module.agent.domain.context_domain import _prefix_hash
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route a client's per-call AsyncClient through a MockTransport."""
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        del args
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


def _deepseek_client() -> DeepSeekClient:
    return DeepSeekClient(
        api_key="test-key",
        base_url="https://example.invalid",
        model="deepseek-reasoner",
        timeout_seconds=1.0,
        max_tokens=1_800,
        chat_max_tokens=8_000,
        temperature=0.0,
        supports_thinking=True,
    )


def _anthropic_client() -> AnthropicClient:
    return AnthropicClient(
        api_key="test-key",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-5",
        timeout_seconds=5.0,
        max_tokens=2_000,
        chat_max_tokens=8_000,
    )


def _deepseek_body(
    *,
    content: str = "Answer",
    reasoning: str | None = None,
    reasoning_tokens: int | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    usage: dict[str, Any] = {
        "prompt_tokens": 5,
        "completion_tokens": 10,
        "total_tokens": 15,
        "prompt_tokens_details": {"cached_tokens": 1},
    }
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return {
        "model": "deepseek-reasoner",
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": usage,
    }


def test_deepseek_non_streaming_captures_reasoning_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reasoning is a separate field, never mixed into the visible text."""
    _install_transport(
        monkeypatch,
        deepseek_client,
        lambda request: httpx.Response(
            200,
            json=_deepseek_body(reasoning="Think first.", reasoning_tokens=7),
        ),
    )

    result = asyncio.run(
        _deepseek_client().complete_chat([{"role": "user", "content": "Hi"}], [])
    )

    assert result.text == "Answer"
    assert result.reasoning == "Think first."
    assert result.usage["reasoning_tokens"] == 7
    assert result.usage["prompt_cache_hit_tokens"] == 1


def test_deepseek_streaming_captures_reasoning_before_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming keeps reasoning out of ``text`` and calls its own callback."""
    lines = (
        'data: {"model":"deepseek-reasoner","choices":[{"delta":'
        '{"reasoning_content":"Think "},"finish_reason":null}]}',
        'data: {"model":"deepseek-reasoner","choices":[{"delta":'
        '{"reasoning_content":"first."},"finish_reason":null}]}',
        'data: {"model":"deepseek-reasoner","choices":[{"delta":'
        '{"content":"Answer"},"finish_reason":"stop"}]}',
        'data: {"model":"deepseek-reasoner","choices":[],"usage":'
        '{"prompt_tokens":5,"completion_tokens":10,"total_tokens":15,'
        '"completion_tokens_details":{"reasoning_tokens":7}}}',
        "data: [DONE]",
    )
    _install_transport(
        monkeypatch,
        deepseek_client,
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="\n\n".join(lines) + "\n\n",
        ),
    )

    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []

    async def on_reasoning(delta: str) -> None:
        reasoning_chunks.append(delta)

    async def on_text(delta: str) -> None:
        text_chunks.append(delta)

    result = asyncio.run(
        _deepseek_client().complete_chat(
            [{"role": "user", "content": "Hi"}],
            [],
            stream=True,
            on_text_delta=on_text,
            on_reasoning_delta=on_reasoning,
        )
    )

    assert reasoning_chunks == ["Think ", "first."]
    assert text_chunks == ["Answer"]
    assert result.reasoning == "Think first."
    assert result.text == "Answer"
    assert result.usage["reasoning_tokens"] == 7
    assert "reasoning_content" not in result.raw_assistant_message
    assert "Think" not in result.raw_assistant_message["content"]


def test_deepseek_without_reasoning_stays_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No provider reasoning means no captured text and no usage key."""
    _install_transport(
        monkeypatch,
        deepseek_client,
        lambda request: httpx.Response(200, json=_deepseek_body()),
    )

    result = asyncio.run(
        _deepseek_client().complete_chat([{"role": "user", "content": "Hi"}], [])
    )

    assert result.reasoning == ""
    assert "reasoning_tokens" not in result.usage


def _message_body(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 4,
        },
    }


def _sse(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(
        f"event: {name}\ndata: {json.dumps(payload)}\n\n"
        for name, payload in events
    )


def test_anthropic_non_streaming_captures_thinking_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A returned thinking block is preserved without changing the request."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=_message_body(
                [
                    {"type": "thinking", "thinking": "Consider it."},
                    {"type": "text", "text": "Answer"},
                ]
            ),
        )

    _install_transport(monkeypatch, anthropic_client, handler)

    result = asyncio.run(
        _anthropic_client().complete_chat([{"role": "user", "content": "Hi"}], [])
    )

    assert result.text == "Answer"
    assert result.reasoning == "Consider it."
    sent = json.loads(requests[0].content)
    assert "thinking" not in sent
    assert "budget_tokens" not in json.dumps(sent)


def test_anthropic_streaming_captures_thinking_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamed thinking deltas reach the reasoning callback, not the text."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=_sse(
                [
                    (
                        "message_start",
                        {
                            "type": "message_start",
                            "message": {
                                "model": "claude-sonnet-5",
                                "usage": {"input_tokens": 10},
                            },
                        },
                    ),
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {
                                "type": "thinking",
                                "thinking": "First",
                            },
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {
                                "type": "thinking_delta",
                                "thinking": " second",
                            },
                        },
                    ),
                    (
                        "content_block_stop",
                        {"type": "content_block_stop", "index": 0},
                    ),
                    (
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 1,
                            "content_block": {"type": "text", "text": ""},
                        },
                    ),
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": 1,
                            "delta": {"type": "text_delta", "text": "Answer"},
                        },
                    ),
                    (
                        "content_block_stop",
                        {"type": "content_block_stop", "index": 1},
                    ),
                    (
                        "message_delta",
                        {
                            "type": "message_delta",
                            "delta": {"stop_reason": "end_turn"},
                            "usage": {"output_tokens": 4},
                        },
                    ),
                    ("message_stop", {"type": "message_stop"}),
                ]
            ),
        )

    _install_transport(monkeypatch, anthropic_client, handler)
    reasoning_chunks: list[str] = []
    text_chunks: list[str] = []

    async def on_reasoning(delta: str) -> None:
        reasoning_chunks.append(delta)

    async def on_text(delta: str) -> None:
        text_chunks.append(delta)

    result = asyncio.run(
        _anthropic_client().complete_chat(
            [{"role": "user", "content": "Hi"}],
            [],
            stream=True,
            on_text_delta=on_text,
            on_reasoning_delta=on_reasoning,
        )
    )

    assert reasoning_chunks == ["First", " second"]
    assert text_chunks == ["Answer"]
    assert result.reasoning == "First second"
    assert result.text == "Answer"
    sent = json.loads(requests[0].content)
    assert "thinking" not in sent


def _new_conversation(client: TestClient, title: str) -> int:
    response = client.post(
        "/api/v1/agent/conversations",
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _assistant_entries(client: TestClient, conversation_id: int) -> list[Any]:
    detail = client.get(
        f"/api/v1/agent/conversations/{conversation_id}"
    ).json()
    return [
        entry for entry in detail["entries"] if entry["kind"] == "pi.assistant"
    ]


def test_reasoning_stream_event_precedes_text_and_is_persisted(
    client: TestClient,
) -> None:
    """`reasoning_delta` is ordered before text and never changes `message_end`."""
    reasoning = "先確認問題，再計算。"
    fake = FakeChatGenerator(
        [
            text_result(
                "答案是 2。",
                reasoning=reasoning,
                usage={
                    "prompt_tokens": 21,
                    "completion_tokens": 6,
                    "total_tokens": 27,
                    "reasoning_tokens": 12,
                },
            )
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client, "Reasoning stream")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "一加一等於多少？"},
    )
    assert response.status_code == 200, response.text
    body = response.text

    reasoning_index = body.index("event: reasoning_delta")
    text_index = body.index("event: message_delta")
    assert reasoning_index < text_index
    assert (
        'event: reasoning_delta\ndata: {"entry_id":null,"delta":"先確認問題，再計算。"}'
        in body
    )
    message_delta_line = next(
        line
        for line in body.splitlines()
        if line.startswith('data: {"entry_id":null,"delta":"答案是')
    )
    assert "reasoning" not in message_delta_line
    message_end = next(
        line
        for line in body.splitlines()
        if line.startswith('data: {"entry_id":')
        and '"finish_reason":"stop"' in line
    )
    payload = json.loads(message_end.removeprefix("data: "))
    assert set(payload) == {"entry_id", "usage", "finish_reason"}

    entries = _assistant_entries(client, conversation_id)
    assert len(entries) == 1
    data = entries[0]["data"]
    assert data["reasoning"] == reasoning
    assert data["reasoning_chars"] == len(reasoning)
    assert data["reasoning_truncated"] is False
    assert data["reasoning_tokens"] == 12
    assert entries[0]["model"][0]["content"] == "答案是 2。"
    assert reasoning not in json.dumps(entries[0]["model"], ensure_ascii=False)


def test_reasoning_delta_precedes_the_corresponding_tool_events(
    client: TestClient,
) -> None:
    """Tool-call reasoning is emitted before the tool starts, not after it."""
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "calculate",
                {"expression": "1 + 1"},
                call_id="call_reasoning_order",
                reasoning="Check the expression first.",
            ),
            text_result("The answer is 2."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client, "Reasoning tool order")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Add one and one."},
    )
    assert response.status_code == 200, response.text
    body = response.text

    assert body.index("event: reasoning_delta") < body.index("event: tool_start")
    assert body.index("event: reasoning_delta") < body.index("event: tool_end")


def test_reasoning_never_enters_provider_messages_or_cache_prefix_hash(
    client: TestClient,
) -> None:
    """The provider sees the assistant text and tool calls only."""
    reasoning = "PRIVATE-REASONING-MARKER"
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "calculate",
                {"expression": "1 + 1"},
                call_id="call_reasoning",
                reasoning=reasoning,
            ),
            text_result("The answer is 2."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client, "Reasoning isolation")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Add one and one."},
    )
    assert response.status_code == 200, response.text
    assert len(fake.requests) == 2

    sent = json.dumps(fake.requests[1].messages, ensure_ascii=False)
    assert reasoning not in sent
    assert "reasoning_content" not in sent

    first_request = fake.requests[0]
    expected_hash = _prefix_hash(first_request.messages[0], first_request.tools)
    entries = _assistant_entries(client, conversation_id)
    assert entries
    assert all(entry["data"]["cache_prefix_hash"] == expected_hash for entry in entries)
    assert reasoning not in expected_hash


def test_long_reasoning_is_bounded_and_marked_truncated(client: TestClient) -> None:
    """The transcript keeps a bounded prefix and records the original size."""
    reasoning = "r" * (MAX_ASSISTANT_REASONING_CHARS + 50)
    fake = FakeChatGenerator([text_result("Answer.", reasoning=reasoning)])
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client, "Reasoning truncation")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Think hard."},
    )
    assert response.status_code == 200, response.text

    entries = _assistant_entries(client, conversation_id)
    data = entries[0]["data"]
    assert data["reasoning_chars"] == len(reasoning)
    assert data["reasoning_truncated"] is True
    assert len(data["reasoning"]) <= MAX_ASSISTANT_REASONING_CHARS


def test_absent_reasoning_adds_no_placeholder(client: TestClient) -> None:
    """A provider that returns no reasoning produces no event and no data key."""
    fake = FakeChatGenerator([text_result("Answer.")])
    client.app.state.agent_chat_generator = fake
    conversation_id = _new_conversation(client, "No reasoning")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Just answer."},
    )
    assert response.status_code == 200, response.text
    assert "event: reasoning_delta" not in response.text

    entries = _assistant_entries(client, conversation_id)
    assert "reasoning" not in entries[0]["data"]
    assert "reasoning_tokens" not in entries[0]["data"]
