"""Chat provider contract used by the agent loop."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

TextDeltaCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ChatToolCall:
    """One tool call requested by the model."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str | None = None


@dataclass(frozen=True)
class ChatResult:
    """One assistant completion plus provider metadata."""

    text: str
    tool_calls: list[ChatToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    raw_assistant_message: dict[str, Any] = field(default_factory=dict)


class ChatGeneratorProtocol(Protocol):
    """The provider surface required by the persistent agent.

    The knowledge slice keeps using its smaller ``TextGeneratorProtocol``.
    ``complete_text`` and ``complete_json`` stay available on the same concrete
    client, so summaries, query expansion, and settings are unaffected.
    """

    configured: bool
    model_name: str

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult: ...
