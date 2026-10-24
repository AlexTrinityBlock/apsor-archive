"""DeepSeek chat-completions client (OpenAI-compatible).

The same client implements the knowledge slice's small text/JSON protocol and the
agent slice's message-list chat protocol. Streaming tool-call arguments are
accumulated by index and only parsed after the stream completes; partial JSON is
never persisted.
"""

import json
import logging
from typing import Any

import httpx

from app.module.agent.protocol.chat_generator_protocol import (
    ChatResult,
    ChatToolCall,
    TextDeltaCallback,
)
from app.module.knowledge.exception.domain_error import AiNotConfiguredError, AiProviderError
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """The only place that knows the DeepSeek HTTP contract."""

    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        temperature: float,
        supports_thinking: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.supports_thinking = supports_thinking

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _base_payload(self, model: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.supports_thinking:
            payload["thinking"] = {"type": "disabled"}
        return payload

    async def _complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
    ) -> AiCompletion:
        payload = self._base_payload(None)
        payload["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload["stream"] = False
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AiProviderError(f"network error: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise AiProviderError(f"HTTP {response.status_code}: {detail}")
        try:
            body = response.json()
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiProviderError("malformed completion response") from exc
        if not isinstance(text, str) or not text.strip():
            raise AiProviderError("empty completion")

        usage = _normalize_usage(body.get("usage")) if isinstance(body, dict) else {}
        model = body.get("model") if isinstance(body, dict) else None
        return AiCompletion(
            text=text.strip(),
            model=str(model or self.model_name),
            usage=usage,
        )

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        """Run one chat completion, optionally streaming text deltas."""
        payload = self._base_payload(model)
        payload["messages"] = messages
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        should_stream = stream or on_text_delta is not None
        payload["stream"] = should_stream
        if should_stream:
            payload["stream_options"] = {"include_usage": True}
            return await self._stream_chat(payload, on_text_delta)
        return await self._chat_once(payload)

    async def _chat_once(self, payload: dict[str, Any]) -> ChatResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AiProviderError(f"network error: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise AiProviderError(f"HTTP {response.status_code}: {detail}")
        try:
            body = response.json()
            choice = body["choices"][0]
            if not isinstance(choice, dict):
                raise AiProviderError("malformed chat response")
            message = choice.get("message") or {}
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiProviderError("malformed chat response") from exc
        if not isinstance(message, dict):
            raise AiProviderError("malformed chat response")

        text = message.get("content")
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise AiProviderError("malformed chat response")
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        if not text.strip() and not tool_calls:
            raise AiProviderError("empty completion")
        finish_reason = str(choice.get("finish_reason") or ("tool_calls" if tool_calls else "stop"))
        usage = _normalize_usage(body.get("usage"))
        model = body.get("model") or payload.get("model") or self.model_name
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=str(model),
            usage=usage,
            raw_assistant_message=message,
        )

    async def _stream_chat(
        self,
        payload: dict[str, Any],
        on_text_delta: TextDeltaCallback | None,
    ) -> ChatResult:
        content_parts: list[str] = []
        call_slots: dict[int, dict[str, str]] = {}
        finish_reason = ""
        usage: dict[str, int] = {}
        model_name = str(payload.get("model") or self.model_name)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        detail = body.decode("utf-8", errors="replace")[:300].replace("\n", " ")
                        raise AiProviderError(f"HTTP {response.status_code}: {detail}")
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(chunk, dict):
                            continue
                        chunk_usage = chunk.get("usage")
                        if isinstance(chunk_usage, dict):
                            usage = _normalize_usage(chunk_usage)
                        chunk_model = chunk.get("model")
                        if isinstance(chunk_model, str) and chunk_model:
                            model_name = chunk_model
                        choices = chunk.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        choice = choices[0]
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta")
                        if not isinstance(delta, dict):
                            delta = {}
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            content_parts.append(piece)
                            if on_text_delta is not None:
                                await on_text_delta(piece)
                        raw_calls = delta.get("tool_calls")
                        if isinstance(raw_calls, list):
                            _accumulate_tool_calls(call_slots, raw_calls)
                        reason = choice.get("finish_reason")
                        if isinstance(reason, str) and reason:
                            finish_reason = reason
        except httpx.HTTPError as exc:
            raise AiProviderError(f"network error: {exc}") from exc

        text = "".join(content_parts)
        tool_calls = _build_streamed_tool_calls(call_slots)
        if not text.strip() and not tool_calls:
            raise AiProviderError("empty completion")
        resolved_finish = finish_reason or ("tool_calls" if tool_calls else "stop")
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=resolved_finish,
            model=model_name,
            usage=usage,
            raw_assistant_message=_raw_assistant_message(text, tool_calls),
        )


class NullTextGenerator:
    """Fail fast when no AI key is configured."""

    configured = False
    model_name = "unconfigured"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        raise AiNotConfiguredError()


NullChatGenerator = NullTextGenerator


def _normalize_usage(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    usage = {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    details = raw.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        if isinstance(cached, int) and not isinstance(cached, bool):
            usage.setdefault("prompt_cache_hit_tokens", cached)
    return usage


def _parse_tool_calls(raw: object) -> list[ChatToolCall]:
    if not isinstance(raw, list):
        return []
    calls: list[ChatToolCall] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        arguments = function.get("arguments")
        raw_arguments = (
            arguments
            if isinstance(arguments, str)
            else json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
        )
        parsed, parse_error = _parse_arguments(raw_arguments)
        calls.append(
            ChatToolCall(
                call_id=str(item.get("id") or f"call_{index}"),
                name=str(name or "unknown"),
                arguments=parsed,
                raw_arguments=raw_arguments,
                parse_error=parse_error,
            )
        )
    return calls


def _parse_arguments(raw: str) -> tuple[dict[str, Any], str | None]:
    if not raw.strip():
        return {}, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "Tool arguments are not valid JSON."
    if not isinstance(parsed, dict):
        return {}, "Tool arguments must be a JSON object."
    return parsed, None


def _accumulate_tool_calls(
    slots: dict[int, dict[str, str]],
    raw_calls: list[object],
) -> None:
    for position, raw in enumerate(raw_calls):
        if not isinstance(raw, dict):
            continue
        index_value = raw.get("index", position)
        index = index_value if isinstance(index_value, int) else position
        slot = slots.setdefault(index, {"id": "", "name": "", "arguments": ""})
        call_id = raw.get("id")
        if isinstance(call_id, str) and call_id:
            slot["id"] = call_id
        function = raw.get("function")
        if not isinstance(function, dict):
            continue
        name_piece = function.get("name")
        if isinstance(name_piece, str) and name_piece:
            if not slot["name"]:
                slot["name"] = name_piece
            elif name_piece.startswith(slot["name"]):
                slot["name"] = name_piece
            elif not slot["name"].startswith(name_piece):
                slot["name"] += name_piece
        arguments_piece = function.get("arguments")
        if isinstance(arguments_piece, str):
            slot["arguments"] += arguments_piece


def _build_streamed_tool_calls(slots: dict[int, dict[str, str]]) -> list[ChatToolCall]:
    calls: list[ChatToolCall] = []
    for index in sorted(slots):
        slot = slots[index]
        raw_arguments = slot["arguments"] or "{}"
        parsed, parse_error = _parse_arguments(raw_arguments)
        calls.append(
            ChatToolCall(
                call_id=slot["id"] or f"call_{index}",
                name=slot["name"] or "unknown",
                arguments=parsed,
                raw_arguments=raw_arguments,
                parse_error=parse_error,
            )
        )
    return calls


def _raw_assistant_message(
    text: str,
    tool_calls: list[ChatToolCall],
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.raw_arguments,
                },
            }
            for call in tool_calls
        ]
    return message


__all__ = [
    "DeepSeekClient",
    "NullChatGenerator",
    "NullTextGenerator",
]
