"""DeepSeek chat-completions client (OpenAI-compatible).

The same client implements the knowledge slice's small text/JSON protocol and the
agent slice's message-list chat protocol. Streaming tool-call arguments are
accumulated by index and only parsed after the stream completes; partial JSON is
never persisted.
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
    AiNotConfiguredError,
    AiProviderError,
)
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion

logger = logging.getLogger(__name__)

# Status codes where the provider itself declares a temporary condition. A
# request can be retried without changing the payload.
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
_ERROR_MESSAGE_LIMIT = 300


# Endpoint/model pairs that rejected ``reasoning_effort`` with a 400. Once a
# retry without the field succeeds, every later call in this process omits it,
# so a model without reasoning support never fails because of an assignment.
_EFFORT_UNSUPPORTED: set[tuple[str, str]] = set()


def effort_unsupported(base_url: str, model: str) -> bool:
    """Return whether ``model`` at ``base_url`` rejected ``reasoning_effort``."""
    return (base_url.rstrip("/"), model) in _EFFORT_UNSUPPORTED


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
        chat_max_tokens: int | None = None,
        temperature: float,
        supports_thinking: bool = True,
        reasoning_effort: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        # Chat turns may need to emit long tool arguments, while summaries and
        # JSON extraction should keep the smaller extraction budget. A chat cap
        # of 0 or None means unlimited: the payload omits max_tokens entirely.
        self.chat_max_tokens = chat_max_tokens or 0
        # Some OpenAI-compatible providers reject a max_tokens value above their
        # own limit. Once a retry without the field succeeds, every later chat
        # call in this process omits it.
        self._chat_cap_rejected = False
        self._chat_cap_warning_logged = False
        self.temperature = temperature
        self.supports_thinking = supports_thinking
        # Free-text effort from the account assignment. Empty means "omit the
        # field and let the provider default apply"; it is never validated here.
        self.reasoning_effort = reasoning_effort

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def max_output_tokens(self) -> int:
        """The completion-token cap for one agent chat call; 0 means unlimited."""
        if self._chat_cap_rejected:
            return 0
        return self.chat_max_tokens

    def _effective_effort(
        self,
        override: str | None,
        model: str | None = None,
    ) -> str | None:
        """Return the effort to send, or ``None`` when the field must be omitted."""
        if effort_unsupported(self.base_url, model or self.model_name):
            return None
        value = self.reasoning_effort if override is None else override
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _effort_rejection(
        self,
        payload: dict[str, Any],
        status_code: int,
        body: bytes,
    ) -> bool:
        """Return whether a 400 rejected ``reasoning_effort``, not something else."""
        return (
            status_code == 400
            and "reasoning_effort" in payload
            and b"reasoning" in body.lower()
        )

    def _without_effort(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remember the rejection and return the payload without the effort."""
        model = str(payload.get("model") or self.model_name)
        _EFFORT_UNSUPPORTED.add((self.base_url, model))
        logger.warning(
            "provider rejected reasoning_effort; retrying without it "
            "provider=deepseek model=%s status=400",
            model or "-",
        )
        trimmed = dict(payload)
        trimmed.pop("reasoning_effort", None)
        if self.supports_thinking:
            trimmed["thinking"] = {"type": "disabled"}
        return trimmed

    def _base_payload(
        self,
        model: str | None,
        *,
        chat: bool = False,
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model_name,
            "temperature": self.temperature,
        }
        cap = (
            max_tokens
            if max_tokens is not None
            else (self.chat_max_tokens if chat else self.max_tokens)
        )
        if cap and not (chat and self._chat_cap_rejected):
            payload["max_tokens"] = cap
        effort = self._effective_effort(reasoning_effort, model or self.model_name)
        if effort is not None:
            # The modern OpenAI-style field replaces the legacy switch: sending
            # both would make some gateways reject the request.
            payload["reasoning_effort"] = effort
        elif self.supports_thinking:
            payload["thinking"] = {"type": "disabled"}
        return payload

    def _chat_cap_rejection(
        self,
        payload: dict[str, Any],
        status_code: int,
        body: bytes,
    ) -> bool:
        """Return whether a 400 rejected the chat output cap, not something else."""
        return (
            status_code == 400
            and "max_tokens" in payload
            and b"max_tokens" in body.lower()
        )

    def _note_chat_cap_fallback(self, model: str) -> None:
        """Log the one fallback warning without the request body or credentials."""
        if self._chat_cap_warning_logged:
            return
        self._chat_cap_warning_logged = True
        logger.warning(
            "provider rejected chat max_tokens; retrying once without the cap "
            "provider=deepseek model=%s status=400",
            model or "-",
        )

    async def _complete(
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
        payload = self._base_payload(
            model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
        )
        payload["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload["stream"] = False
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=False,
            messages=2,
            tools=0,
            max_tokens=payload.get("max_tokens"),
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
                if self._effort_rejection(payload, response.status_code, response.content):
                    payload = self._without_effort(payload)
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
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
            # The raw body is never logged. A bounded provider error code and
            # message are logged so an operator can classify the failure.
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
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
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
        if not isinstance(text, str) or not text.strip():
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

        usage = _normalize_usage(body.get("usage")) if isinstance(body, dict) else {}
        response_model = body.get("model") if isinstance(body, dict) else None
        result = AiCompletion(
            text=text.strip(),
            model=str(response_model or request_model),
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

    async def probe(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 16,
    ) -> AiCompletion:
        """Run one tiny non-streaming generation to validate a connection."""
        return await self._complete(
            system_prompt="You are a connection test.",
            user_prompt="Reply with the single word OK.",
            json_mode=False,
            model=model,
            max_tokens=max_tokens,
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
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        """Run one chat completion, optionally streaming text deltas."""
        payload = self._base_payload(model, chat=True)
        payload["messages"] = messages
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        should_stream = (
            stream or on_text_delta is not None or on_reasoning_delta is not None
        )
        payload["stream"] = should_stream
        if should_stream:
            payload["stream_options"] = {"include_usage": True}
            return await self._stream_chat(
                payload,
                on_text_delta,
                on_reasoning_delta,
            )
        return await self._chat_once(payload)

    async def _chat_once(self, payload: dict[str, Any]) -> ChatResult:
        operation = "chat"
        call_id = uuid4().hex[:12]
        model = str(payload.get("model") or self.model_name)
        stream = False
        started = time.monotonic()
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=model,
            stream=stream,
            messages=len(payload.get("messages") or []),
            tools=len(payload.get("tools") or []),
            max_tokens=payload.get("max_tokens"),
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
        )
        fallback_used = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
                if self._effort_rejection(payload, response.status_code, response.content):
                    payload = self._without_effort(payload)
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
                if self._chat_cap_rejection(
                    payload,
                    response.status_code,
                    response.content,
                ):
                    fallback_used = True
                    self._note_chat_cap_fallback(model)
                    payload = _payload_without_max_tokens(payload)
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
        except httpx.HTTPError as exc:
            raise _network_error(
                exc,
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
                started=started,
            ) from exc
        request_id = _response_request_id(response)
        if response.status_code >= 400:
            raise _http_error(
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
                status_code=response.status_code,
                request_id=request_id,
                body=response.content,
                started=started,
            )
        if fallback_used:
            self._chat_cap_rejected = True
        try:
            body = response.json()
            choice = body["choices"][0]
            if not isinstance(choice, dict):
                raise AiProviderError("malformed chat response")
            message = choice.get("message") or {}
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
                response=response,
                started=started,
                reason="malformed_response",
            )
            raise AiProviderError(
                "malformed chat response",
                status_code=response.status_code,
                provider_request_id=request_id,
            ) from exc
        if not isinstance(message, dict):
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
                response=response,
                started=started,
                reason="malformed_message",
            )
            raise AiProviderError(
                "malformed chat response",
                status_code=response.status_code,
                provider_request_id=request_id,
            )

        text = message.get("content")
        if text is None:
            text = ""
        if not isinstance(text, str):
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
                response=response,
                started=started,
                reason="malformed_content",
            )
            raise AiProviderError(
                "malformed chat response",
                status_code=response.status_code,
                provider_request_id=request_id,
            )
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        if not text.strip() and not tool_calls:
            _log_invalid_response(
                operation=operation,
                call_id=call_id,
                model=model,
                stream=stream,
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
        finish_reason = str(choice.get("finish_reason") or ("tool_calls" if tool_calls else "stop"))
        usage = _normalize_usage(body.get("usage"))
        reasoning = message.get("reasoning_content")
        if not isinstance(reasoning, str):
            reasoning = ""
        response_model = body.get("model") or payload.get("model") or self.model_name
        result = ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=str(response_model),
            usage=usage,
            raw_assistant_message=message,
            reasoning=reasoning,
        )
        _log_request_completed(
            operation=operation,
            call_id=call_id,
            model=model,
            stream=stream,
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
        on_reasoning_delta: TextDeltaCallback | None,
    ) -> ChatResult:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        call_slots: dict[int, dict[str, str]] = {}
        finish_reason = ""
        usage: dict[str, int] = {}
        model_name = str(payload.get("model") or self.model_name)
        operation = "chat"
        call_id = uuid4().hex[:12]
        request_model = model_name
        started = time.monotonic()
        chunk_count = 0
        first_chunk_ms: int | None = None
        response_status: int | None = None
        response_request_id: str | None = None
        response_content_type: str | None = None
        _log_request_started(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=True,
            messages=len(payload.get("messages") or []),
            tools=len(payload.get("tools") or []),
            max_tokens=payload.get("max_tokens"),
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
        )

        fallback_used = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                while True:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    ) as response:
                        response_status = response.status_code
                        response_request_id = _response_request_id(response)
                        response_content_type = response.headers.get("content-type")
                        if response.status_code >= 400:
                            body = await response.aread()
                            if self._effort_rejection(
                                payload,
                                response.status_code,
                                body,
                            ):
                                payload = self._without_effort(payload)
                                continue
                            if self._chat_cap_rejection(
                                payload,
                                response.status_code,
                                body,
                            ):
                                fallback_used = True
                                self._note_chat_cap_fallback(request_model)
                                payload = _payload_without_max_tokens(payload)
                                continue
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
                            chunk_count += 1
                            if first_chunk_ms is None:
                                first_chunk_ms = _elapsed_ms(started)
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
                            reasoning_piece = delta.get("reasoning_content")
                            if isinstance(reasoning_piece, str) and reasoning_piece:
                                reasoning_parts.append(reasoning_piece)
                                if on_reasoning_delta is not None:
                                    await on_reasoning_delta(reasoning_piece)
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
                        break
        except httpx.HTTPError as exc:
            raise _network_error(
                exc,
                operation=operation,
                call_id=call_id,
                model=request_model,
                stream=True,
                started=started,
            ) from exc
        if fallback_used:
            self._chat_cap_rejected = True

        text = "".join(content_parts)
        tool_calls = _build_streamed_tool_calls(call_slots)
        if not text.strip() and not tool_calls:
            logger.warning(
                "provider response invalid provider=deepseek operation=%s "
                "call_id=%s model=%s stream=true status=%s duration_ms=%d "
                "request_id=%s content_type=%s chunks=%d "
                "reason=empty_completion retryable=true",
                operation,
                call_id,
                request_model,
                response_status,
                _elapsed_ms(started),
                response_request_id or "-",
                response_content_type or "-",
                chunk_count,
            )
            raise AiProviderError(
                "empty completion",
                status_code=response_status,
                retryable=True,
                provider_request_id=response_request_id,
            )
        resolved_finish = finish_reason or ("tool_calls" if tool_calls else "stop")
        result = ChatResult(
            text=text,
            tool_calls=tool_calls,
            finish_reason=resolved_finish,
            model=model_name,
            usage=usage,
            raw_assistant_message=_raw_assistant_message(text, tool_calls),
            reasoning="".join(reasoning_parts),
        )
        _log_request_completed(
            operation=operation,
            call_id=call_id,
            model=request_model,
            stream=True,
            status_code=response_status or 200,
            request_id=response_request_id,
            started=started,
            finish_reason=resolved_finish,
            response_model=model_name,
            text_chars=len(text),
            tool_names=[call.name for call in tool_calls],
            chunks=chunk_count,
            first_chunk_ms=first_chunk_ms,
            usage=usage,
        )
        return result


class NullTextGenerator:
    """Fail fast when no AI key is configured."""

    configured = False
    model_name = "unconfigured"
    max_output_tokens = 0

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()

    async def probe(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 16,
    ) -> AiCompletion:
        del model, reasoning_effort, max_tokens
        raise AiProviderError("provider not configured", retryable=False)

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        raise AiNotConfiguredError()


NullChatGenerator = NullTextGenerator


_CONTEXT_ERROR_MARKERS = (
    "context_length_exceeded",
    "maximum context length",
    "context length",
    "too many tokens",
    "prompt is too long",
)


def _log_request_started(
    *,
    operation: str,
    call_id: str,
    model: str,
    stream: bool,
    messages: int,
    tools: int,
    max_tokens: int | None,
    temperature: float,
    timeout_seconds: float,
) -> None:
    logger.info(
        "provider request started provider=deepseek operation=%s call_id=%s "
        "model=%s stream=%s messages=%d tools=%d max_tokens=%s "
        "temperature=%s timeout_s=%s",
        operation,
        call_id,
        model or "-",
        stream,
        messages,
        tools,
        max_tokens if max_tokens is not None else "-",
        temperature,
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
        "provider request completed provider=deepseek operation=%s call_id=%s "
        "model=%s stream=%s status=%d duration_ms=%d request_id=%s "
        "finish_reason=%s response_model=%s text_chars=%d tool_calls=%d "
        "tool_names=%s chunks=%s first_chunk_ms=%s prompt_tokens=%d "
        "completion_tokens=%d total_tokens=%d cached_tokens=%d",
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
        usage.get("prompt_cache_hit_tokens", 0),
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
        "provider response invalid provider=deepseek operation=%s call_id=%s "
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
    """Classify an HTTP failure and log bounded provider error metadata.

    The raw response body is deliberately never logged: it can echo request
    metadata. Only the provider's own error code/type/message, clipped to a
    fixed length, is recorded for diagnosis.
    """
    error_code, error_type, error_message = _error_metadata(body)
    context_window = _is_context_window_error(body)
    retryable = _is_retryable_status(status_code)
    logger.warning(
        "provider request failed provider=deepseek operation=%s call_id=%s "
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
        error_code or "-",
        error_type or "-",
        error_message or "-",
        len(body),
        "context_window" if context_window else "http_error",
        retryable,
    )
    if context_window:
        return AiContextWindowError()
    detail = f"HTTP {status_code}"
    if error_code:
        detail += f" ({error_code})"
    if error_message:
        detail += f": {error_message}"
    return AiProviderError(
        detail,
        status_code=status_code,
        retryable=retryable,
        provider_request_id=request_id,
        provider_error_code=error_code,
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
        "provider request failed provider=deepseek operation=%s call_id=%s "
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


def _response_request_id(response: httpx.Response) -> str | None:
    for header in ("x-request-id", "x-ds-request-id", "cf-ray"):
        value = response.headers.get(header)
        if value:
            return value
    return None


def _error_metadata(body: bytes) -> tuple[str | None, str | None, str | None]:
    """Extract the provider's bounded error fields, never the raw body."""
    try:
        payload = json.loads(body[:8192].decode("utf-8", "ignore"))
    except ValueError:
        return None, None, None
    if not isinstance(payload, dict):
        return None, None, None
    error = payload.get("error")
    if isinstance(error, dict):
        return (
            _clip_error_text(error.get("code")),
            _clip_error_text(error.get("type")),
            _clip_error_text(error.get("message")),
        )
    return None, None, _clip_error_text(payload.get("message"))


def _clip_error_text(value: object, limit: int = _ERROR_MESSAGE_LIMIT) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS_CODES


def _is_context_window_error(body: bytes) -> bool:
    text = body[:8192].decode("utf-8", "ignore").lower()
    return any(marker in text for marker in _CONTEXT_ERROR_MARKERS)


def _payload_without_max_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(payload)
    trimmed.pop("max_tokens", None)
    return trimmed


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
    completion_details = raw.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning_tokens = completion_details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int) and not isinstance(reasoning_tokens, bool):
            usage["reasoning_tokens"] = reasoning_tokens
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


_TRAILING_STRUCTURE_CHARS = frozenset("}] \t\r\n\f\v")


def _parse_arguments(raw: str) -> tuple[dict[str, Any], str | None]:
    """Parse one tool-call argument string.

    Some providers emit a complete JSON object followed by extra closing
    braces. That is not truncation: the object is whole and only the tail is
    junk, so a bounded prefix parse is safe. The leftover may contain nothing
    but whitespace and closing brackets, and the prefix must itself be a JSON
    object. Every other failure, including truncated JSON, stays an error.
    """
    if not raw.strip():
        return {}, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        if error.msg == "Extra data":
            repaired = _parse_object_before_trailing_junk(raw, error.pos)
            if repaired is not None:
                return repaired, None
        return {}, _invalid_json_detail(error)
    if not isinstance(parsed, dict):
        return {}, _json_type_detail(parsed)
    return parsed, None


def _invalid_json_detail(error: json.JSONDecodeError) -> str:
    """Describe a JSON failure without echoing the offending argument text."""
    return _bounded_argument_detail(
        f"Tool arguments are not valid JSON: {error.msg} at line "
        f"{error.lineno} column {error.colno}."
    )


def _json_type_detail(value: object) -> str:
    """Name the observed JSON type of a non-object argument document."""
    if value is None:
        kind = "null"
    elif isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, list):
        kind = "array"
    elif isinstance(value, str):
        kind = "string"
    elif isinstance(value, (int, float)):
        kind = "number"
    else:
        kind = type(value).__name__
    return _bounded_argument_detail(
        f"Tool arguments must be a JSON object, got {kind}."
    )


def _bounded_argument_detail(detail: str) -> str:
    """Collapse whitespace and cap one model-facing parse error at 300 chars."""
    return " ".join(detail.split())[:300]


def _parse_object_before_trailing_junk(raw: str, position: int) -> dict[str, Any] | None:
    """Return the complete object before provider-appended closing brackets."""
    remainder = raw[position:]
    if any(character not in _TRAILING_STRUCTURE_CHARS for character in remainder):
        return None
    try:
        parsed = json.loads(raw[:position])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
