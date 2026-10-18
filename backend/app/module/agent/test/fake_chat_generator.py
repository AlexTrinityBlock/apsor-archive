"""Deterministic chat-generator seam for agent integration tests.

This module contains no tests. The test agent can import it and inject an
instance through ``app.state.agent_chat_generator`` or by overriding
``get_agent_chat_generator``.
"""

import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.module.agent.protocol.chat_generator_protocol import (
    ChatGeneratorProtocol,
    ChatResult,
    ChatToolCall,
    TextDeltaCallback,
)


@dataclass(frozen=True)
class FakeChatRequest:
    """One recorded provider request."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    model: str | None


class FakeChatGenerator:
    """Return scripted results and stream text in deterministic chunks."""

    configured = True
    model_name = "fake-chat"

    def __init__(
        self,
        results: Sequence[ChatResult] | None = None,
        *,
        chunk_size: int = 24,
    ) -> None:
        self._results: deque[ChatResult] = deque(results or [])
        self.chunk_size = max(1, chunk_size)
        self.requests: list[FakeChatRequest] = []
        self.streamed_text: list[str] = []

    def enqueue(self, result: ChatResult) -> None:
        """Append one scripted completion."""
        self._results.append(result)

    @property
    def remaining(self) -> int:
        """Number of scripted completions still waiting."""
        return len(self._results)

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        del stream
        self.requests.append(
            FakeChatRequest(
                messages=[dict(message) for message in messages],
                tools=[dict(tool) for tool in tools],
                model=model,
            )
        )
        if not self._results:
            raise RuntimeError("FakeChatGenerator has no scripted completion left.")
        result = self._results.popleft()
        if on_text_delta is not None and result.text:
            for start in range(0, len(result.text), self.chunk_size):
                chunk = result.text[start : start + self.chunk_size]
                self.streamed_text.append(chunk)
                await on_text_delta(chunk)
        return result

    @classmethod
    def from_texts(
        cls,
        *texts: str,
        usage: dict[str, int] | None = None,
    ) -> "FakeChatGenerator":
        """Build a generator from plain final answers."""
        return cls(
            [
                text_result(text, usage=usage)
                for text in texts
            ]
        )


def text_result(
    text: str,
    *,
    usage: dict[str, int] | None = None,
    finish_reason: str = "stop",
) -> ChatResult:
    """Build a normal assistant text result."""
    resolved_usage = usage or {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "prompt_cache_hit_tokens": 6,
        "prompt_cache_miss_tokens": 4,
    }
    return ChatResult(
        text=text,
        finish_reason=finish_reason,
        model="fake-chat",
        usage=resolved_usage,
        raw_assistant_message={"role": "assistant", "content": text},
    )


def tool_call_result(
    name: str,
    arguments: dict[str, Any],
    *,
    call_id: str = "call_1",
    text: str = "",
    usage: dict[str, int] | None = None,
) -> ChatResult:
    """Build a tool-call-only assistant result."""
    raw_arguments = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ChatResult(
        text=text,
        tool_calls=[
            ChatToolCall(
                call_id=call_id,
                name=name,
                arguments=arguments,
                raw_arguments=raw_arguments,
            )
        ],
        finish_reason="tool_calls",
        model="fake-chat",
        usage=usage
        or {
            "prompt_tokens": 12,
            "completion_tokens": 6,
            "total_tokens": 18,
            "prompt_cache_hit_tokens": 8,
            "prompt_cache_miss_tokens": 4,
        },
        raw_assistant_message={
            "role": "assistant",
            "content": text,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": raw_arguments,
                    },
                }
            ],
        },
    )


__all__ = [
    "ChatGeneratorProtocol",
    "FakeChatGenerator",
    "FakeChatRequest",
    "TextDeltaCallback",
    "text_result",
    "tool_call_result",
]
