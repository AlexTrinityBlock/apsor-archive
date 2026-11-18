"""Ordered provider-chain fallbacks for the four AI capabilities.

A capability may have several active provider rows. The runtime builds one
client per entry and wraps them here; consumers keep using the same protocols and
therefore obtain automatic failover without knowing about the chain.

The rules are intentionally conservative:

* Text, JSON, embedding, search, and fetch move to the next entry on a provider
  or transport failure.
* Agent chat only fails over before the first streamed text delta. Once output
  reached the caller, switching providers would duplicate visible text, so the
  error is re-raised.
* Context-window and output-limit errors are never failed over; the agent owns
  compaction and the bounded output retry.
* The notice reporter is invoked once, only after the entire chain failed, and
  its own failure can never mask the provider exception.
"""

import logging
from collections.abc import Sequence
from typing import Any, Literal, cast

from app.module.agent.protocol.chat_generator_protocol import (
    ChatGeneratorProtocol,
    ChatResult,
    TextDeltaCallback,
)
from app.module.knowledge.domain.provider_config_domain import ProviderCapability
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiNotConfiguredError,
    EmbeddingProviderError,
)
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_builder_protocol import WebClientProtocol
from app.module.knowledge.protocol.provider_notice_protocol import (
    ProviderAttempt,
    ProviderFailureEvent,
    ProviderFailureReporter,
)
from app.module.knowledge.protocol.text_generator_protocol import (
    AiCompletion,
    TextGeneratorProtocol,
)
from app.module.web_research.exception.domain_error import (
    WebProviderAuthenticationError,
    WebProviderError,
)

logger = logging.getLogger(__name__)

# A provider may reject the exact request (bad input or a plan/quota cap) while
# the next provider in the chain could accept it. Those errors still fail over,
# but they are expected client-side conditions rather than a system outage, so
# they never create a persistent root notice.
_EXPECTED_STATUS_CODES = frozenset({400, 402, 413, 422, 429})
_EXPECTED_MARKERS = (
    "invalid request",
    "validation",
    "quota",
    "rate limit",
    "too many requests",
)
_NON_FAILOVER_CHAT_MARKERS = (
    "context length",
    "context window",
    "maximum context",
    "output limit",
    "output token limit",
    "finish_reason=length",
)


def _configured_clients[T](entries: Sequence[tuple[str, T]]) -> list[tuple[str, T]]:
    """Drop clients whose own ``configured`` flag is false."""
    return [
        (name, client)
        for name, client in entries
        if bool(getattr(client, "configured", False))
    ]


def _status_code(exc: BaseException) -> int | None:
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _error_code(exc: BaseException) -> str:
    """Return a stable, bounded code for one failed provider call."""
    provider_code = getattr(exc, "provider_error_code", None)
    if isinstance(provider_code, str) and provider_code.strip():
        return " ".join(provider_code.split())[:64]
    status = _status_code(exc)
    if status is not None:
        return f"http_{status}"
    if isinstance(exc, WebProviderAuthenticationError):
        return "authentication_error"
    name = type(exc).__name__.strip()
    return (name or "provider_error")[:64]


def _detail(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def _attempt(name: str, exc: BaseException) -> ProviderAttempt:
    return ProviderAttempt(
        provider=name,
        status_code=_status_code(exc),
        error_code=_error_code(exc),
        detail=_detail(exc),
    )


def _is_expected_error(exc: BaseException) -> bool:
    """Whether the failure is an input/quota condition, not an outage."""
    if isinstance(exc, AiNotConfiguredError):
        return True
    if _status_code(exc) in _EXPECTED_STATUS_CODES:
        return True
    lowered = _detail(exc).lower()
    return any(marker in lowered for marker in _EXPECTED_MARKERS)


def _is_non_failover_chat_error(exc: BaseException) -> bool:
    """Context and output limits are handled by the agent, not a backup."""
    if isinstance(exc, AiContextWindowError):
        return True
    if type(exc).__name__ in {"AgentOutputLimitError", "AiOutputLimitError"}:
        return True
    lowered = _detail(exc).lower()
    return any(marker in lowered for marker in _NON_FAILOVER_CHAT_MARKERS)


async def _report(
    reporter: ProviderFailureReporter | None,
    *,
    capability: ProviderCapability,
    operation: str,
    exc: BaseException,
    attempts: list[ProviderAttempt],
) -> None:
    """Send one whole-chain failure event; never replace the provider error."""
    if reporter is None or _is_expected_error(exc):
        return
    event = ProviderFailureEvent(
        capability=capability,
        operation=operation,
        error_code=_error_code(exc),
        status_code=_status_code(exc),
        detail=_detail(exc),
        attempts=tuple(attempts),
    )
    try:
        await reporter(event)
    except Exception:
        logger.warning(
            "provider failure notice could not be recorded capability=%s operation=%s",
            capability,
            operation,
        )


def _log_failover(
    *,
    capability: ProviderCapability,
    operation: str,
    failed: str,
    code: str,
) -> None:
    logger.warning(
        "provider fallback capability=%s operation=%s failed_provider=%s error_code=%s",
        capability,
        operation,
        failed,
        code,
    )


class FallbackTextGenerator:
    """Try an ordered chat chain for text, JSON, and streamed agent calls."""

    def __init__(
        self,
        entries: Sequence[tuple[str, TextGeneratorProtocol]],
        *,
        reporter: ProviderFailureReporter | None = None,
    ) -> None:
        self._entries = tuple(entries)
        self._reporter = reporter

    def _usable(self) -> list[tuple[str, TextGeneratorProtocol]]:
        return _configured_clients(self._entries)

    @property
    def configured(self) -> bool:
        return bool(self._usable())

    @property
    def model_name(self) -> str:
        for _name, client in self._usable():
            return str(getattr(client, "model_name", "unconfigured"))
        return "unconfigured"

    @property
    def max_output_tokens(self) -> int:
        for _name, client in self._usable():
            value = getattr(client, "max_output_tokens", 0)
            return value if isinstance(value, int) else 0
        return 0

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete_textual(
            "text",
            system_prompt,
            user_prompt,
            json_mode=False,
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete_textual(
            "json",
            system_prompt,
            user_prompt,
            json_mode=True,
        )

    async def _complete_textual(
        self,
        operation: Literal["text", "json"],
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool,
    ) -> AiCompletion:
        entries = self._usable()
        if not entries:
            raise AiNotConfiguredError()
        attempts: list[ProviderAttempt] = []
        last_error: BaseException | None = None
        for name, client in entries:
            try:
                if json_mode:
                    return await client.complete_json(system_prompt, user_prompt)
                return await client.complete_text(system_prompt, user_prompt)
            except Exception as exc:
                if isinstance(exc, AiNotConfiguredError):
                    raise
                attempts.append(_attempt(name, exc))
                last_error = exc
                _log_failover(
                    capability="chat",
                    operation=operation,
                    failed=name,
                    code=_error_code(exc),
                )
        if last_error is None:  # pragma: no cover - entries is non-empty.
            raise AiNotConfiguredError()
        await _report(
            self._reporter,
            capability="chat",
            operation=operation,
            exc=last_error,
            attempts=attempts,
        )
        raise last_error

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatResult:
        entries = [
            (index, name, client)
            for index, (name, client) in enumerate(self._entries)
            if bool(getattr(client, "configured", False))
        ]
        if not entries:
            raise AiNotConfiguredError()
        attempts: list[ProviderAttempt] = []
        last_error: BaseException | None = None
        for chain_index, name, client in entries:
            emitted = False

            async def tracked_delta(piece: str) -> None:
                nonlocal emitted
                emitted = True
                if on_text_delta is not None:
                    await on_text_delta(piece)

            try:
                return await cast(ChatGeneratorProtocol, client).complete_chat(
                    messages,
                    tools,
                    # The primary honours the conversation's model. A backup
                    # uses its own configured model so a chain may mix vendors.
                    model=model if chain_index == 0 else None,
                    stream=stream,
                    on_text_delta=tracked_delta if on_text_delta is not None else None,
                )
            except Exception as exc:
                if _is_non_failover_chat_error(exc):
                    raise
                attempts.append(_attempt(name, exc))
                last_error = exc
                if emitted:
                    # The caller already received text; a second provider would
                    # duplicate visible output, so the chain stops here.
                    await _report(
                        self._reporter,
                        capability="chat",
                        operation="chat",
                        exc=exc,
                        attempts=attempts,
                    )
                    raise
                _log_failover(
                    capability="chat",
                    operation="chat",
                    failed=name,
                    code=_error_code(exc),
                )
        if last_error is None:  # pragma: no cover - entries is non-empty.
            raise AiNotConfiguredError()
        await _report(
            self._reporter,
            capability="chat",
            operation="chat",
            exc=last_error,
            attempts=attempts,
        )
        raise last_error


class FallbackEmbedder:
    """Try embedding backups that share the primary's model and dimension.

    Different vector models live in different spaces, so mixing them would make
    the per-owner vector index meaningless. Mismatched backups are skipped
    defensively even though the provider service rejects such a chain at write
    time (a legacy row or a direct database edit may still exist).
    """

    def __init__(
        self,
        entries: Sequence[tuple[str, EmbedderProtocol]],
        *,
        reporter: ProviderFailureReporter | None = None,
    ) -> None:
        self._reporter = reporter
        self._primary_name, primary = entries[0] if entries else ("none", None)
        if primary is None:
            self._entries: tuple[tuple[str, EmbedderProtocol], ...] = ()
            self.model_name = "none"
            self.dimension = 0
            return
        self.model_name = primary.model_name
        self.dimension = primary.dimension
        kept: list[tuple[str, EmbedderProtocol]] = []
        for name, embedder in entries:
            if (
                embedder.dimension != primary.dimension
                or embedder.model_name != primary.model_name
            ):
                logger.warning(
                    "embedding fallback skipped provider=%s model=%s dimension=%s "
                    "reason=incompatible_with_primary model_expected=%s "
                    "dimension_expected=%s",
                    name,
                    getattr(embedder, "model_name", "-"),
                    getattr(embedder, "dimension", "-"),
                    primary.model_name,
                    primary.dimension,
                )
                continue
            kept.append((name, embedder))
        # A disabled primary (dimension 0) means the capability is off; a
        # configured-looking backup must not silently switch it on.
        self._entries = tuple(kept) if primary.dimension > 0 else ()

    @property
    def provider(self) -> str:
        return self._primary_name

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._entries:
            raise EmbeddingProviderError("Embeddings are disabled.")
        attempts: list[ProviderAttempt] = []
        last_error: BaseException | None = None
        for name, embedder in self._entries:
            try:
                return await embedder.embed(texts)
            except EmbeddingProviderError as exc:
                attempts.append(_attempt(name, exc))
                last_error = exc
                _log_failover(
                    capability="embedding",
                    operation="embed",
                    failed=name,
                    code=_error_code(exc),
                )
        if last_error is None:  # pragma: no cover - entries is non-empty.
            raise EmbeddingProviderError("Embeddings are disabled.")
        await _report(
            self._reporter,
            capability="embedding",
            operation="embed",
            exc=last_error,
            attempts=attempts,
        )
        raise last_error


class FallbackWebClient:
    """Try ordered web search/fetch providers on provider or auth failures."""

    def __init__(
        self,
        entries: Sequence[tuple[str, WebClientProtocol]],
        *,
        capability: ProviderCapability,
        reporter: ProviderFailureReporter | None = None,
    ) -> None:
        if capability not in {"web_search", "web_fetch"}:  # pragma: no cover - caller.
            raise ValueError("FallbackWebClient only handles web capabilities.")
        self._entries = tuple(entries)
        self._capability = capability
        self._reporter = reporter
        self.provider = entries[0][0] if entries else "none"

    @property
    def configured(self) -> bool:
        return bool(_configured_clients(self._entries))

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
        objective: str = "",
    ) -> Any:
        entries = _configured_clients(self._entries)
        if not entries:
            raise WebProviderError("No web search provider is configured.")
        attempts: list[ProviderAttempt] = []
        last_error: BaseException | None = None
        for name, client in entries:
            try:
                return await client.search(
                    query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    objective=objective,
                )
            except (WebProviderError, WebProviderAuthenticationError) as exc:
                attempts.append(_attempt(name, exc))
                last_error = exc
                _log_failover(
                    capability=self._capability,
                    operation="search",
                    failed=name,
                    code=_error_code(exc),
                )
        if last_error is None:  # pragma: no cover - entries is non-empty.
            raise WebProviderError("No web search provider is configured.")
        await _report(
            self._reporter,
            capability=self._capability,
            operation="search",
            exc=last_error,
            attempts=attempts,
        )
        raise last_error

    async def fetch(self, url: str, *, max_chars: int) -> Any:
        entries = _configured_clients(self._entries)
        if not entries:
            raise WebProviderError("No web fetch provider is configured.")
        attempts: list[ProviderAttempt] = []
        last_error: BaseException | None = None
        for name, client in entries:
            try:
                return await client.fetch(url, max_chars=max_chars)
            except (WebProviderError, WebProviderAuthenticationError) as exc:
                attempts.append(_attempt(name, exc))
                last_error = exc
                _log_failover(
                    capability=self._capability,
                    operation="fetch",
                    failed=name,
                    code=_error_code(exc),
                )
        if last_error is None:  # pragma: no cover - entries is non-empty.
            raise WebProviderError("No web fetch provider is configured.")
        await _report(
            self._reporter,
            capability=self._capability,
            operation="fetch",
            exc=last_error,
            attempts=attempts,
        )
        raise last_error


# Re-exported for the runtime and tests: the fallback classes are the only
# consumer of these exception families, and importing them here keeps the
# classification rules in one place.
__all__ = [
    "FallbackEmbedder",
    "FallbackTextGenerator",
    "FallbackWebClient",
]
