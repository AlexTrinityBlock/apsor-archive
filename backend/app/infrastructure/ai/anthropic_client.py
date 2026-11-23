"""Native Anthropic Messages API client.

This adapter implements both surfaces the application consumes: the knowledge
slice's small text/JSON protocol and the agent slice's message-list chat
protocol. It speaks ``POST /v1/messages`` directly, including the named-event
SSE stream, so no OpenAI compatibility layer is involved.

The client is intentionally stateless between calls and creates its
``httpx.AsyncClient`` inside each request. It never sends sampling controls
(they were removed in the Anthropic version this adapter targets) and never
logs a key, a prompt, or a response body.
"""

import json
import logging
import time
from typing import Any
from uuid import uuid4

import httpx

from app.module.agent.protocol.chat_generator_protocol import (
    ChatResult,
    ChatToolCall,
    TextDeltaCallback,
)
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiProviderError,
)
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion

logger = logging.getLogger(__name__)

# ``max_tokens`` is required by the Messages API. The database cap is the same
# value, so a row cannot request more than this adapter can send.
MAX_ANTHROPIC_OUTPUT_TOKENS = 131_072

_ERROR_MESSAGE_LIMIT = 300
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

_CONTEXT_ERROR_MARKERS = (
    "context_length_exceeded",
    "maximum context length",
    "context length",
    "too many tokens",
    "prompt is too long",
    "input length and max_tokens exceed context limit",
)

_JSON_ONLY_INSTRUCTION = "Return only one valid JSON object and nothing else."

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "refusal": "refusal",
}


class AnthropicClient:
    """The only place that knows the Anthropic HTTP and SSE contract."""

    configured = True
    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        chat_max_tokens: int | None = None,
        anthropic_version: str = "2026-10-21",
        reasoning_effort: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        # The shared background cap (text/JSON/vision) and the larger agent
        # chat cap. Unlike the OpenAI-compatible client, this API cannot omit
        # max_tokens, so an absent chat cap falls back to the shared cap.
        self.max_tokens = _clamp_tokens(max_tokens)
        self.chat_max_tokens = _clamp_tokens(chat_max_tokens or max_tokens)
        self.anthropic_version = anthropic_version
        self.reasoning_effort = reasoning_effort

    @property
    def max_output_tokens(self) -> int:
        """The completion-token cap for one agent chat call."""
        return self.chat_max_tokens

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete_textual(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete_textual(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

    async def probe(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 16,
    ) -> AiCompletion:
        """Run one tiny non-streaming generation to validate a connection."""
        return await self._complete_textual(
            system_prompt="You are a connection test.",
            user_prompt="Reply with the single word OK.",
            json_mode=False,
            model=model,
            max_tokens=_clamp_tokens(max_tokens),
            reasoning_effort=reasoning_effort,
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
        system_blocks, translated_messages, translated_tools = _translate_request(
            messages, tools
        )
        should_stream = stream or on_text_delta is not None
        request_model = model or self.model_name
        payload: dict[str, Any] = {
            "model": request_model,
            "max_tokens": self.chat_max_tokens,
            "messages": translated_messages,
            "stream": should_stream,
        }
        if system_blocks:
            payload["system"] = system_blocks
        if translated_tools:
            payload["tools"] = translated_tools
            # Prompt caching is only worth its breakpoints when a stable tool
            # prefix exists. ``complete_text``/``complete_json`` send none.
            _apply_cache_breakpoints(payload)
        effort = self._effective_effort(None)
        if effort is not None:
            payload["output_config"] = {"effort": effort}
        if should_stream:
            return await self._stream_chat(payload, on_text_delta)
        return await self._chat_once(payload)

    def _effective_effort(self, override: str | None) -> str | None:
        """Return the effort to send, or None when the field must be omitted."""
        value = self.reasoning_effort if override is None else override
        if isinstance(value, str) and value.strip():
            return value
        return None

    async def _complete_textual(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        model: str | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> AiCompletion:
        operation = "complete_json" if json_mode else "complete_text"
        call_id = uuid4().hex[:12]
        request_model = model or self.model_name
        started = time.monotonic()
        system_text = (
            _with_json_instruction(system_prompt) if json_mode else system_prompt
        )
        payload: dict[str, Any] = {
            "model": request_model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False,
        }
        if system_text.strip():
            payload["system"] = system_text
        effort = self._effective_effort(reasoning_effort)
        if effort is not None:
            payload["output_config"] = {"effort": effort}
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=False,
            messages=1,
            tools=0,
            max_tokens=payload["max_tokens"],
            effort=effort,
            timeout_seconds=self.timeout_seconds,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    _messages_url(self.base_url),
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _network_error(
                exc,
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                started=started,
            ) from exc

        request_id = _response_request_id(response)
        if response.status_code >= 400:
            raise _http_error(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                status_code=response.status_code,
                request_id=request_id,
                body=response.content,
                started=started,
            )
        try:
            body = response.json()
            content = body["content"]
        except (KeyError, TypeError, ValueError) as exc:
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="malformed_response",
            )
            raise AiProviderError(
                "malformed completion response",
                status_code=response.status_code,
                provider_request_id=request_id,
            ) from exc
        if not isinstance(content, list):
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="malformed_content",
            )
            raise AiProviderError(
                "malformed completion response",
                status_code=response.status_code,
                provider_request_id=request_id,
            )
        text, _tool_calls = _parse_content_blocks(content)
        if not text.strip():
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="empty_completion",
            )
            raise AiProviderError(
                "empty completion",
                status_code=response.status_code,
                retryable=True,
                provider_request_id=request_id,
            )
        if json_mode:
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise AiProviderError(
                    "invalid JSON completion",
                    status_code=response.status_code,
                    provider_request_id=request_id,
                    provider_error_message=_clip_error_text(exc.msg),
                ) from exc

        usage = _normalize_anthropic_usage(body.get("usage"))
        response_model = body.get("model") or payload["model"]
        result = AiCompletion(
            text=text.strip(),
            model=str(response_model),
            usage=usage,
        )
        _log_request_completed(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=False,
            status_code=response.status_code,
            request_id=request_id,
            started=started,
            finish_reason="complete",
            response_model=result.model,
            text_chars=len(result.text),
            tool_names=[],
            chunks=None,
            first_chunk_ms=None,
            usage=result.usage,
        )
        return result

    async def _chat_once(self, payload: dict[str, Any]) -> ChatResult:
        operation = "chat"
        call_id = uuid4().hex[:12]
        request_model = str(payload.get("model") or self.model_name)
        started = time.monotonic()
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=False,
            messages=len(payload.get("messages") or []),
            tools=len(payload.get("tools") or []),
            max_tokens=payload.get("max_tokens"),
            effort=_payload_effort(payload),
            timeout_seconds=self.timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    _messages_url(self.base_url),
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise _network_error(
                exc,
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                started=started,
            ) from exc

        request_id = _response_request_id(response)
        if response.status_code >= 400:
            raise _http_error(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                status_code=response.status_code,
                request_id=request_id,
                body=response.content,
                started=started,
            )
        try:
            body = response.json()
            content = body["content"]
        except (KeyError, TypeError, ValueError) as exc:
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="malformed_response",
            )
            raise AiProviderError(
                "malformed chat response",
                status_code=response.status_code,
                provider_request_id=request_id,
            ) from exc
        if not isinstance(content, list):
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="malformed_content",
            )
            raise AiProviderError(
                "malformed chat response",
                status_code=response.status_code,
                provider_request_id=request_id,
            )
        text, tool_calls = _parse_content_blocks(content)
        if not text.strip() and not tool_calls:
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=False,
                response=response,
                started=started,
                reason="empty_completion",
            )
            raise AiProviderError(
                "empty completion",
                status_code=response.status_code,
                retryable=True,
                provider_request_id=request_id,
            )
        finish_reason = _finish_reason(body.get("stop_reason"), tool_calls)
        usage = _normalize_anthropic_usage(body.get("usage"))
        response_model = body.get("model") or payload["model"]
        result = ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=str(response_model),
            usage=usage,
            raw_assistant_message=_raw_assistant_message(text, tool_calls),
        )
        _log_request_completed(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=False,
            status_code=response.status_code,
            request_id=request_id,
            started=started,
            finish_reason=finish_reason,
            response_model=result.model,
            text_chars=len(result.text),
            tool_names=[call.name for call in result.tool_calls],
            chunks=None,
            first_chunk_ms=None,
            usage=result.usage,
        )
        return result

    async def _stream_chat(
        self,
        payload: dict[str, Any],
        on_text_delta: TextDeltaCallback | None,
    ) -> ChatResult:
        operation = "chat"
        call_id = uuid4().hex[:12]
        request_model = str(payload.get("model") or self.model_name)
        started = time.monotonic()
        response_status: int | None = None
        response_request_id: str | None = None
        first_chunk_ms: int | None = None
        state = _AnthropicStreamState()
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=True,
            messages=len(payload.get("messages") or []),
            tools=len(payload.get("tools") or []),
            max_tokens=payload.get("max_tokens"),
            effort=_payload_effort(payload),
            timeout_seconds=self.timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    _messages_url(self.base_url),
                    headers=self._headers,
                    json=payload,
                ) as response:
                    response_status = response.status_code
                    response_request_id = _response_request_id(response)
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise _http_error(
                            operation=operation,
                            call_id=call_id,
                            model=request_model,
                            stream=True,
                            status_code=response.status_code,
                            request_id=response_request_id,
                            body=body,
                            started=started,
                        )
                    event_name = ""
                    data_lines: list[str] = []
                    async for raw_line in response.aiter_lines():
                        line = raw_line.rstrip("\r")
                        if line == "":
                            if data_lines:
                                if first_chunk_ms is None:
                                    first_chunk_ms = _elapsed_ms(started)
                                await _dispatch_event(
                                    event_name,
                                    data_lines,
                                    state,
                                    on_text_delta,
                                    response_request_id,
                                )
                                data_lines = []
                            event_name = ""
                            continue
                        if line.startswith(":"):
                            continue
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data = line[5:]
                            if data.startswith(" "):
                                data = data[1:]
                            data_lines.append(data)
                    if data_lines:
                        if first_chunk_ms is None:
                            first_chunk_ms = _elapsed_ms(started)
                        await _dispatch_event(
                            event_name,
                            data_lines,
                            state,
                            on_text_delta,
                            response_request_id,
                        )
        except httpx.HTTPError as exc:
            raise _network_error(
                exc,
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=True,
                started=started,
            ) from exc

        state.finalize_open_blocks()
        if not state.saw_stop:
            logger.warning(
                "provider response invalid provider=anthropic operation=%s "
                "call_id=%s model=%s stream=true status=%s duration_ms=%d "
                "request_id=%s events=%d reason=truncated_stream retryable=true",
                operation,
                call_id,
                request_model,
                response_status,
                _elapsed_ms(started),
                response_request_id or "-",
                state.event_count,
            )
            raise AiProviderError(
                "truncated stream",
                status_code=response_status,
                retryable=True,
                provider_request_id=response_request_id,
            )
        text = "".join(state.text_parts)
        tool_calls = state.tool_calls
        if not text.strip() and not tool_calls:
            logger.warning(
                "provider response invalid provider=anthropic operation=%s "
                "call_id=%s model=%s stream=true status=%s duration_ms=%d "
                "request_id=%s events=%d reason=empty_completion retryable=true",
                operation,
                call_id,
                request_model,
                response_status,
                _elapsed_ms(started),
                response_request_id or "-",
                state.event_count,
            )
            raise AiProviderError(
                "empty completion",
                status_code=response_status,
                retryable=True,
                provider_request_id=response_request_id,
            )
        finish_reason = _finish_reason(state.stop_reason, tool_calls)
        response_model = state.model or request_model
        result = ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=response_model,
            usage=_normalize_anthropic_usage(state.usage_raw),
            raw_assistant_message=_raw_assistant_message(text, tool_calls),
        )
        _log_request_completed(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=True,
            status_code=response_status or 200,
            request_id=response_request_id,
            started=started,
            finish_reason=finish_reason,
            response_model=result.model,
            text_chars=len(text),
            tool_names=[call.name for call in tool_calls],
            chunks=state.event_count,
            first_chunk_ms=first_chunk_ms,
            usage=result.usage,
        )
        return result


class _AnthropicStreamState:
    """Accumulated named events for one streamed Messages response."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tool_slots: dict[int, dict[str, Any]] = {}
        self.tool_calls: list[ChatToolCall] = []
        self.usage_raw: dict[str, Any] = {}
        self.stop_reason = ""
        self.saw_stop = False
        self.model = ""
        self.event_count = 0

    async def consume(
        self,
        event_name: str,
        payload: dict[str, Any],
        on_text_delta: TextDeltaCallback | None,
        request_id: str | None,
    ) -> None:
        raw_kind = payload.get("type")
        kind = raw_kind if isinstance(raw_kind, str) and raw_kind else event_name
        self.event_count += 1
        if kind == "ping":
            return
        if kind == "error":
            raise _stream_error(payload, request_id)
        if kind == "message_start":
            message = payload.get("message")
            if isinstance(message, dict):
                model = message.get("model")
                if isinstance(model, str) and model:
                    self.model = model
                usage = message.get("usage")
                if isinstance(usage, dict):
                    self.usage_raw.update(usage)
            return
        if kind == "content_block_start":
            index = _int_or(payload.get("index"), 0)
            block = payload.get("content_block")
            if not isinstance(block, dict):
                return
            block_type = block.get("type")
            if block_type == "text":
                initial = block.get("text")
                if isinstance(initial, str) and initial:
                    self.text_parts.append(initial)
                    if on_text_delta is not None:
                        await on_text_delta(initial)
            elif block_type == "tool_use":
                initial_input = block.get("input")
                self.tool_slots[index] = {
                    "id": block.get("id") if isinstance(block.get("id"), str) else "",
                    "name": (
                        block.get("name") if isinstance(block.get("name"), str) else ""
                    ),
                    "json": "",
                    "initial": (
                        initial_input if isinstance(initial_input, dict) else None
                    ),
                }
            return
        if kind == "content_block_delta":
            index = _int_or(payload.get("index"), 0)
            delta = payload.get("delta")
            if not isinstance(delta, dict):
                return
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                piece = delta.get("text")
                if isinstance(piece, str) and piece:
                    self.text_parts.append(piece)
                    if on_text_delta is not None:
                        await on_text_delta(piece)
            elif delta_type == "input_json_delta":
                slot = self.tool_slots.setdefault(
                    index,
                    {"id": "", "name": "", "json": "", "initial": None},
                )
                piece = delta.get("partial_json")
                if isinstance(piece, str):
                    slot["json"] += piece
            # thinking_delta and signature_delta are deliberately ignored.
            return
        if kind == "content_block_stop":
            index = _int_or(payload.get("index"), 0)
            stopped_slot = self.tool_slots.get(index)
            if stopped_slot is not None:
                del self.tool_slots[index]
                self.tool_calls.append(_slot_tool_call(stopped_slot, index))
            return
        if kind == "message_delta":
            delta = payload.get("delta")
            if isinstance(delta, dict):
                stop_reason = delta.get("stop_reason")
                if isinstance(stop_reason, str) and stop_reason:
                    self.stop_reason = stop_reason
            usage = payload.get("usage")
            if isinstance(usage, dict):
                self.usage_raw.update(usage)
            return
        if kind == "message_stop":
            self.saw_stop = True

    def finalize_open_blocks(self) -> None:
        """Close tool blocks a gateway left open before ``message_stop``."""
        for index in sorted(self.tool_slots):
            self.tool_calls.append(_slot_tool_call(self.tool_slots[index], index))
        self.tool_slots.clear()


async def _dispatch_event(
    event_name: str,
    data_lines: list[str],
    state: _AnthropicStreamState,
    on_text_delta: TextDeltaCallback | None,
    request_id: str | None,
) -> None:
    """Decode one buffered SSE event; malformed data is skipped, not fatal."""
    raw = "\n".join(data_lines)
    if not raw.strip() or raw.strip() == "[DONE]":
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "provider stream event ignored provider=anthropic reason=invalid_json "
            "event=%s data_bytes=%d",
            event_name or "-",
            len(raw),
        )
        return
    if not isinstance(payload, dict):
        return
    await state.consume(event_name, payload, on_text_delta, request_id)


def _messages_url(base_url: str) -> str:
    """Resolve the Messages endpoint for the supported base-URL shapes."""
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def _translate_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Hoist system messages, translate blocks, and merge same-role turns."""
    system_parts: list[str] = []
    translated: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "system":
            text = _content_text(message.get("content"))
            if text:
                system_parts.append(text)
            continue
        target_role, blocks = _translate_message(message)
        if not target_role or not blocks:
            continue
        if translated and translated[-1]["role"] == target_role:
            translated[-1]["content"].extend(blocks)
        else:
            translated.append({"role": target_role, "content": blocks})
    if translated and translated[-1]["role"] == "assistant":
        raise AiProviderError(
            "assistant prefill is not supported",
            retryable=False,
        )
    if not translated:
        raise AiProviderError("empty conversation", retryable=False)
    system_blocks = (
        [{"type": "text", "text": "\n\n".join(system_parts)}] if system_parts else []
    )
    return system_blocks, translated, _translate_tools(tools)


def _translate_message(
    message: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    role = message.get("role")
    if role == "assistant":
        blocks: list[dict[str, Any]] = []
        text = _content_text(message.get("content"))
        if text:
            blocks.append({"type": "text", "text": text})
        raw_calls = message.get("tool_calls")
        if isinstance(raw_calls, list):
            for index, raw_call in enumerate(raw_calls):
                block = _tool_use_block(raw_call, index)
                if block is not None:
                    blocks.append(block)
        return "assistant", blocks
    if role == "tool":
        block = _tool_result_block(message)
        return "user", [block] if block is not None else []
    if role == "user":
        return "user", _translate_content(message.get("content"))
    return "", []


def _content_text(content: object) -> str:
    """Flatten a string or text-block list into one string."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _translate_content(content: object) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return []
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                blocks.append({"type": "text", "text": text})
        elif part_type == "image_url":
            image = part.get("image_url")
            url = image.get("url") if isinstance(image, dict) else None
            block = _image_block(url)
            if block is not None:
                blocks.append(block)
        elif part_type == "image":
            source = part.get("source")
            if isinstance(source, dict):
                blocks.append({"type": "image", "source": dict(source)})
    return blocks


def _image_block(url: object) -> dict[str, Any] | None:
    """Convert one ``data:<mime>;base64,...`` URL into an Anthropic image block."""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    header, separator, payload = url.partition(",")
    if not separator or not payload:
        return None
    metadata = header[len("data:") :]
    if ";base64" not in metadata:
        return None
    media_type = metadata.split(";", 1)[0] or "application/octet-stream"
    data = "".join(payload.split())
    if not data:
        return None
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def _tool_result_block(message: dict[str, Any]) -> dict[str, Any] | None:
    call_id = message.get("tool_call_id")
    if not isinstance(call_id, str) or not call_id:
        return None
    content = message.get("content")
    if isinstance(content, list):
        blocks = _translate_content(content)
        value: str | list[dict[str, Any]] = blocks if blocks else ""
    elif isinstance(content, str):
        value = content
    elif content is None:
        value = ""
    else:
        value = str(content)
    return {
        "type": "tool_result",
        "tool_use_id": call_id,
        "content": value,
    }


def _tool_use_block(raw_call: object, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_call, dict):
        return None
    function = raw_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = raw_call.get("name")
        arguments = raw_call.get("arguments")
    if not isinstance(name, str) or not name:
        return None
    call_id = raw_call.get("id")
    parsed, _error = _parse_arguments(arguments)
    return {
        "type": "tool_use",
        "id": call_id if isinstance(call_id, str) and call_id else f"call_{index}",
        "name": name,
        "input": parsed,
    }


def _translate_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            description = function.get("description")
            parameters = function.get("parameters")
        else:
            name = tool.get("name")
            description = tool.get("description")
            parameters = tool.get("input_schema")
        if not isinstance(name, str) or not name.strip():
            continue
        translated.append(
            {
                "name": name,
                "description": description if isinstance(description, str) else "",
                "input_schema": (
                    parameters
                    if isinstance(parameters, dict)
                    else {"type": "object", "properties": {}}
                ),
            }
        )
    return translated


def _apply_cache_breakpoints(payload: dict[str, Any]) -> None:
    """Mark the stable tool prefix, system block, and newest turn for caching."""
    tools = payload.get("tools")
    if isinstance(tools, list) and tools and isinstance(tools[-1], dict):
        tools[-1].setdefault("cache_control", {"type": "ephemeral"})
    system = payload.get("system")
    if isinstance(system, list) and system and isinstance(system[-1], dict):
        system[-1].setdefault("cache_control", {"type": "ephemeral"})
    messages = payload.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[-1], dict):
        content = messages[-1].get("content")
        if isinstance(content, list) and content and isinstance(content[-1], dict):
            content[-1].setdefault("cache_control", {"type": "ephemeral"})


def _parse_content_blocks(
    content: list[object],
) -> tuple[str, list[ChatToolCall]]:
    text_parts: list[str] = []
    tool_calls: list[ChatToolCall] = []
    for index, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        elif block_type == "tool_use":
            tool_calls.append(_tool_call_from_block(block, index))
    return "".join(text_parts), tool_calls


def _tool_call_from_block(block: dict[str, Any], index: int) -> ChatToolCall:
    call_id = block.get("id")
    name = block.get("name")
    raw_input = block.get("input")
    if isinstance(raw_input, dict):
        arguments = raw_input
        parse_error = None
        raw_arguments = _json_arguments(raw_input)
    else:
        arguments = {}
        parse_error = "Tool arguments must be a JSON object."
        raw_arguments = _json_arguments(raw_input) if raw_input is not None else "{}"
    return ChatToolCall(
        call_id=call_id if isinstance(call_id, str) and call_id else f"call_{index}",
        name=name if isinstance(name, str) and name else "unknown",
        arguments=arguments,
        raw_arguments=raw_arguments,
        parse_error=parse_error,
    )


def _slot_tool_call(slot: dict[str, Any], index: int) -> ChatToolCall:
    buffered = slot.get("json")
    raw = buffered if isinstance(buffered, str) else ""
    initial = slot.get("initial")
    if raw.strip():
        arguments, parse_error = _parse_arguments(raw)
        raw_arguments = raw
    elif isinstance(initial, dict) and initial:
        arguments, parse_error = initial, None
        raw_arguments = _json_arguments(initial)
    else:
        arguments, parse_error = {}, None
        raw_arguments = "{}"
    call_id = slot.get("id")
    name = slot.get("name")
    return ChatToolCall(
        call_id=call_id if isinstance(call_id, str) and call_id else f"call_{index}",
        name=name if isinstance(name, str) and name else "unknown",
        arguments=arguments,
        raw_arguments=raw_arguments,
        parse_error=parse_error,
    )


def _parse_arguments(value: object) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, dict):
        return value, None
    if value is None:
        return {}, None
    if not isinstance(value, str):
        return {}, "Tool arguments must be a JSON object."
    if not value.strip():
        return {}, None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        return {}, _bounded_argument_detail(
            f"Tool arguments are not valid JSON: {error.msg} at line "
            f"{error.lineno} column {error.colno}."
        )
    if not isinstance(parsed, dict):
        return {}, "Tool arguments must be a JSON object."
    return parsed, None


def _bounded_argument_detail(detail: str) -> str:
    return " ".join(detail.split())[:_ERROR_MESSAGE_LIMIT]


def _json_arguments(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return "{}"


def _finish_reason(stop_reason: object, tool_calls: list[ChatToolCall]) -> str:
    if isinstance(stop_reason, str) and stop_reason:
        return _STOP_REASON_MAP.get(stop_reason, "stop")
    return "tool_calls" if tool_calls else "stop"


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


def _normalize_anthropic_usage(raw: object) -> dict[str, int]:
    """Map Anthropic's cache buckets onto the repository's OpenAI-shaped keys."""
    if not isinstance(raw, dict):
        return {}
    uncached = _usage_int(raw.get("input_tokens"))
    write = _usage_int(raw.get("cache_creation_input_tokens"))
    read = _usage_int(raw.get("cache_read_input_tokens"))
    output = _usage_int(raw.get("output_tokens"))
    total_input = uncached + write + read
    return {
        "input_tokens": uncached,
        "cache_creation_input_tokens": write,
        "cache_read_input_tokens": read,
        "prompt_tokens": total_input,
        "completion_tokens": output,
        "total_tokens": total_input + output,
        "prompt_cache_hit_tokens": read,
        "cached_tokens": read,
    }


def _usage_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _clamp_tokens(value: int) -> int:
    return max(1, min(int(value), MAX_ANTHROPIC_OUTPUT_TOKENS))


def _with_json_instruction(system_prompt: str) -> str:
    if not system_prompt.strip():
        return _JSON_ONLY_INSTRUCTION
    return f"{system_prompt.rstrip()}\n\n{_JSON_ONLY_INSTRUCTION}"


def _payload_effort(payload: dict[str, Any]) -> str | None:
    output_config = payload.get("output_config")
    if not isinstance(output_config, dict):
        return None
    effort = output_config.get("effort")
    return effort if isinstance(effort, str) else None


def _int_or(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _response_request_id(response: httpx.Response) -> str | None:
    for header in ("request-id", "x-request-id"):
        value = response.headers.get(header)
        if value:
            return value
    return None


def _error_metadata(body: bytes) -> tuple[str | None, str | None, str | None]:
    """Extract bounded provider error fields without retaining the body."""
    try:
        payload = json.loads(body[:8192].decode("utf-8", "ignore"))
    except ValueError:
        return None, None, None
    if not isinstance(payload, dict):
        return None, None, None
    error = payload.get("error")
    if isinstance(error, dict):
        return (
            _clip_error_text(error.get("type")),
            _clip_error_text(error.get("message")),
            _clip_error_text(payload.get("request_id")),
        )
    return (
        _clip_error_text(payload.get("type")),
        _clip_error_text(payload.get("message")),
        _clip_error_text(payload.get("request_id")),
    )


def _clip_error_text(value: object, limit: int = _ERROR_MESSAGE_LIMIT) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def _is_context_window_error(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _CONTEXT_ERROR_MARKERS)


def _http_error(
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    status_code: int,
    request_id: str | None,
    body: bytes,
    started: float,
) -> AiProviderError:
    """Classify an HTTP failure and log bounded metadata, never the body."""
    error_type, error_message, body_request_id = _error_metadata(body)
    request_id = request_id or body_request_id
    raw_text = body[:8192].decode("utf-8", "ignore")
    context_window = (
        status_code == 413
        or error_type == "request_too_large"
        or _is_context_window_error(error_message)
        or _is_context_window_error(raw_text)
    )
    retryable = status_code in _RETRYABLE_STATUS_CODES
    logger.warning(
        "provider request failed provider=anthropic operation=%s call_id=%s "
        "model=%s stream=%s status=%d duration_ms=%d request_id=%s "
        "error_code=%s error_type=%s error_message=%r body_bytes=%d "
        "classification=%s retryable=%s",
        operation,
        call_id,
        model or "-",
        stream,
        status_code,
        _elapsed_ms(started),
        request_id or "-",
        error_type or "-",
        error_type or "-",
        error_message or "-",
        len(body),
        "context_window" if context_window else "http_error",
        retryable,
    )
    if context_window:
        return AiContextWindowError()
    detail = f"HTTP {status_code}"
    if error_type:
        detail += f" ({error_type})"
    if error_message:
        detail += f": {error_message}"
    return AiProviderError(
        detail,
        status_code=status_code,
        retryable=retryable,
        provider_request_id=request_id,
        provider_error_code=error_type,
        provider_error_type=error_type,
        provider_error_message=error_message,
    )


def _stream_error(payload: dict[str, Any], request_id: str | None) -> AiProviderError:
    error = payload.get("error")
    if isinstance(error, dict):
        error_type = _clip_error_text(error.get("type"))
        error_message = _clip_error_text(error.get("message"))
    else:
        error_type = _clip_error_text(payload.get("type"))
        error_message = _clip_error_text(payload.get("message"))
    request_id = _clip_error_text(payload.get("request_id")) or request_id
    if error_type == "request_too_large" or _is_context_window_error(error_message):
        return AiContextWindowError()
    retryable = error_type not in {
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "not_found_error",
    }
    detail = error_message or error_type or "stream error"
    return AiProviderError(
        detail,
        retryable=retryable,
        provider_request_id=request_id,
        provider_error_code=error_type,
        provider_error_type=error_type,
        provider_error_message=error_message,
    )


def _network_error(
    exc: httpx.HTTPError,
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    started: float,
) -> AiProviderError:
    retryable = isinstance(
        exc,
        (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError),
    )
    classification = (
        "timeout" if isinstance(exc, httpx.TimeoutException) else "network_error"
    )
    message = _clip_error_text(str(exc))
    logger.warning(
        "provider request failed provider=anthropic operation=%s call_id=%s "
        "model=%s stream=%s status=network_error duration_ms=%d "
        "error_type=%s error_message=%r classification=%s retryable=%s",
        operation,
        call_id,
        model or "-",
        stream,
        _elapsed_ms(started),
        type(exc).__name__,
        message or "-",
        classification,
        retryable,
    )
    return AiProviderError(
        f"network error ({type(exc).__name__}): {message or 'no detail'}",
        retryable=retryable,
        provider_error_type=type(exc).__name__,
        provider_error_message=message,
    )


def _log_request_started(
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    messages: int,
    tools: int,
    max_tokens: object,
    effort: str | None,
    timeout_seconds: float,
) -> None:
    logger.info(
        "provider request started provider=anthropic operation=%s call_id=%s "
        "model=%s stream=%s messages=%d tools=%d max_tokens=%s effort=%s "
        "timeout_s=%s",
        operation,
        call_id,
        model or "-",
        stream,
        messages,
        tools,
        max_tokens if max_tokens is not None else "-",
        effort or "-",
        timeout_seconds,
    )


def _log_request_completed(
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    status_code: int,
    request_id: str | None,
    started: float,
    finish_reason: str,
    response_model: str,
    text_chars: int,
    tool_names: list[str],
    chunks: int | None,
    first_chunk_ms: int | None,
    usage: dict[str, int],
) -> None:
    logger.info(
        "provider request completed provider=anthropic operation=%s call_id=%s "
        "model=%s stream=%s status=%d duration_ms=%d request_id=%s "
        "finish_reason=%s response_model=%s text_chars=%d tool_calls=%d "
        "tool_names=%s chunks=%s first_chunk_ms=%s prompt_tokens=%d "
        "completion_tokens=%d total_tokens=%d cached_tokens=%d "
        "cache_creation_tokens=%d",
        operation,
        call_id,
        model or "-",
        stream,
        status_code,
        _elapsed_ms(started),
        request_id or "-",
        finish_reason or "-",
        response_model or "-",
        text_chars,
        len(tool_names),
        ",".join(tool_names) if tool_names else "-",
        chunks if chunks is not None else "-",
        first_chunk_ms if first_chunk_ms is not None else "-",
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("total_tokens", 0),
        usage.get("cached_tokens", 0),
        usage.get("cache_creation_input_tokens", 0),
    )


def _log_invalid_response(
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    response: httpx.Response,
    started: float,
    reason: str,
) -> None:
    logger.warning(
        "provider response invalid provider=anthropic operation=%s call_id=%s "
        "model=%s stream=%s status=%d duration_ms=%d request_id=%s "
        "content_type=%s body_bytes=%d reason=%s",
        operation,
        call_id,
        model or "-",
        stream,
        response.status_code,
        _elapsed_ms(started),
        _response_request_id(response) or "-",
        response.headers.get("content-type", "-"),
        len(response.content),
        reason,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = [
    "MAX_ANTHROPIC_OUTPUT_TOKENS",
    "AnthropicClient",
]
