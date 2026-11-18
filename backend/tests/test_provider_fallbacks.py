"""Offline failover behavior for ordered provider chains."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from app.infrastructure.ai.fallbacks import (
    FallbackEmbedder,
    FallbackTextGenerator,
    FallbackWebClient,
)
from app.module.agent.protocol.chat_generator_protocol import ChatResult
from app.module.knowledge.exception.domain_error import (
    AiContextWindowError,
    AiProviderError,
    EmbeddingProviderError,
)
from app.module.knowledge.protocol.provider_notice_protocol import (
    ProviderAttempt,
    ProviderFailureEvent,
)
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion
from app.module.web_research.exception.domain_error import (
    WebProviderAuthenticationError,
    WebProviderError,
)


class _RecordingReporter:
    def __init__(self) -> None:
        self.events: list[ProviderFailureEvent] = []

    async def report(self, event: ProviderFailureEvent) -> None:
        self.events.append(event)


class _FakeChatClient:
    configured = True
    model_name = "fake-primary"
    max_output_tokens = 512

    def __init__(
        self,
        *,
        error: BaseException | None = None,
        delta_before_error: str | None = None,
        chat_result: ChatResult | None = None,
        text_error: BaseException | None = None,
    ) -> None:
        self.error = error
        self.delta_before_error = delta_before_error
        self.chat_result = chat_result or ChatResult(text="ok", model=self.model_name)
        self.text_error = text_error
        self.chat_calls = 0
        self.text_calls = 0

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        self.text_calls += 1
        if self.text_error is not None:
            raise self.text_error
        return AiCompletion(text="text", model=self.model_name, usage={})

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        if self.text_error is not None:
            raise self.text_error
        return AiCompletion(text="{}", model=self.model_name, usage={})

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        stream: bool = False,
        on_text_delta: Callable[[str], Any] | None = None,
    ) -> ChatResult:
        del messages, tools, stream
        self.chat_calls += 1
        self.last_model = model
        if self.delta_before_error and on_text_delta is not None:
            await on_text_delta(self.delta_before_error)
        if self.error is not None:
            raise self.error
        return self.chat_result


class _FakeEmbedder:
    def __init__(
        self,
        *,
        model_name: str = "fake-embed",
        dimension: int = 4,
        error: BaseException | None = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.error = error
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return [[0.1] * self.dimension for _text in texts]


class _FakeWebClient:
    configured = True
    provider = "tavily"

    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error
        self.search_calls = 0
        self.fetch_calls = 0

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: str,
        include_domains: list[str],
        exclude_domains: list[str],
        objective: str = "",
    ) -> object:
        del query, max_results, search_depth, include_domains, exclude_domains, objective
        self.search_calls += 1
        if self.error is not None:
            raise self.error
        return {"kind": "search", "provider": self.provider}

    async def fetch(self, url: str, *, max_chars: int) -> object:
        del url, max_chars
        self.fetch_calls += 1
        if self.error is not None:
            raise self.error
        return {"kind": "fetch", "provider": self.provider}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_chat_primary_fails_before_delta_and_backup_succeeds() -> None:
    reporter = _RecordingReporter()
    primary = _FakeChatClient(error=AiProviderError("primary down"))
    backup = _FakeChatClient(chat_result=ChatResult(text="backup", model="fake-backup"))
    generator = FallbackTextGenerator(
        [("primary", primary), ("backup", backup)],
        reporter=reporter.report,
    )
    deltas: list[str] = []

    async def on_delta(piece: str) -> None:
        deltas.append(piece)

    result = _run(
        generator.complete_chat(
            [{"role": "user", "content": "hi"}],
            [],
            model="caller-model",
            on_text_delta=on_delta,
        )
    )

    assert result.text == "backup"
    assert primary.chat_calls == 1
    assert backup.chat_calls == 1
    assert primary.last_model == "caller-model"
    assert backup.last_model is None
    assert reporter.events == []


def test_chat_skips_unconfigured_primary_and_backup_uses_own_model() -> None:
    primary = _FakeChatClient()
    primary.configured = False
    backup = _FakeChatClient(chat_result=ChatResult(text="backup", model="fake-backup"))
    generator = FallbackTextGenerator([("primary", primary), ("backup", backup)])

    result = _run(
        generator.complete_chat(
            [{"role": "user", "content": "hi"}],
            [],
            model="primary-model",
        )
    )

    assert result.text == "backup"
    assert primary.chat_calls == 0
    assert backup.chat_calls == 1
    # The first configured entry is still a backup in chain order, so it must
    # not receive the primary row's model id.
    assert backup.last_model is None


def test_chat_primary_fails_after_delta_never_calls_backup() -> None:
    reporter = _RecordingReporter()
    primary = _FakeChatClient(
        error=AiProviderError("stream died"),
        delta_before_error="partial",
    )
    backup = _FakeChatClient()
    generator = FallbackTextGenerator(
        [("primary", primary), ("backup", backup)],
        reporter=reporter.report,
    )
    deltas: list[str] = []

    async def on_delta(piece: str) -> None:
        deltas.append(piece)

    with pytest.raises(AiProviderError):
        _run(
            generator.complete_chat(
                [{"role": "user", "content": "hi"}],
                [],
                on_text_delta=on_delta,
            )
        )

    assert deltas == ["partial"]
    assert backup.chat_calls == 0
    assert len(reporter.events) == 1
    assert [attempt.provider for attempt in reporter.events[0].attempts] == ["primary"]


def test_chat_all_providers_fail_reports_once_with_every_attempt() -> None:
    reporter = _RecordingReporter()
    first = _FakeChatClient(error=AiProviderError("one"))
    second = _FakeChatClient(error=AiProviderError("two", status_code=503))
    generator = FallbackTextGenerator(
        [("first", first), ("second", second)],
        reporter=reporter.report,
    )

    with pytest.raises(AiProviderError) as raised:
        _run(
            generator.complete_chat(
                [{"role": "user", "content": "hi"}],
                [],
            )
        )

    assert "two" in str(raised.value)
    assert first.chat_calls == 1
    assert second.chat_calls == 1
    assert len(reporter.events) == 1
    event = reporter.events[0]
    assert event.capability == "chat"
    assert event.operation == "chat"
    assert [attempt.provider for attempt in event.attempts] == ["first", "second"]
    assert [attempt.status_code for attempt in event.attempts] == [None, 503]
    assert event.error_code == "http_503"


def test_chat_context_window_error_does_not_fail_over() -> None:
    primary = _FakeChatClient(error=AiContextWindowError())
    backup = _FakeChatClient()
    generator = FallbackTextGenerator([("primary", primary), ("backup", backup)])

    with pytest.raises(AiContextWindowError):
        _run(generator.complete_chat([{"role": "user", "content": "hi"}], []))

    assert backup.chat_calls == 0


def test_text_all_fail_reports_and_expected_quota_is_not_reported() -> None:
    reporter = _RecordingReporter()
    first = _FakeChatClient(text_error=AiProviderError("boom"))
    second = _FakeChatClient(text_error=AiProviderError("limit", status_code=429))
    generator = FallbackTextGenerator(
        [("first", first), ("second", second)],
        reporter=reporter.report,
    )

    with pytest.raises(AiProviderError):
        _run(generator.complete_text("system", "user"))
    assert first.text_calls == 1
    assert second.text_calls == 1
    # A quota/rate-limit tail is expected and must not create a root notice.
    assert reporter.events == []


def test_reporter_failure_never_masks_the_provider_error() -> None:
    async def broken_reporter(event: ProviderFailureEvent) -> None:
        del event
        raise RuntimeError("database unavailable")

    first = _FakeChatClient(text_error=AiProviderError("provider"))
    generator = FallbackTextGenerator(
        [("first", first)],
        reporter=broken_reporter,
    )

    with pytest.raises(AiProviderError):
        _run(generator.complete_text("system", "user"))


def test_embedding_backup_must_match_the_primary_vector_space() -> None:
    reporter = _RecordingReporter()
    primary = _FakeEmbedder(error=EmbeddingProviderError("401", status_code=401))
    same = _FakeEmbedder()
    mismatch = _FakeEmbedder(model_name="other-model")
    embedder = FallbackEmbedder(
        [("primary", primary), ("same", same), ("mismatch", mismatch)],
        reporter=reporter.report,
    )

    vectors = _run(embedder.embed(["text"]))

    assert vectors == [[0.1] * 4]
    assert embedder.model_name == "fake-embed"
    assert embedder.dimension == 4
    assert primary.calls == 1
    assert same.calls == 1
    assert mismatch.calls == 0
    assert reporter.events == []


def test_embedding_all_fail_reports_and_raises_last() -> None:
    reporter = _RecordingReporter()
    primary = _FakeEmbedder(error=EmbeddingProviderError("first"))
    backup = _FakeEmbedder(error=EmbeddingProviderError("second"))
    embedder = FallbackEmbedder(
        [("primary", primary), ("backup", backup)],
        reporter=reporter.report,
    )

    with pytest.raises(EmbeddingProviderError) as raised:
        _run(embedder.embed(["text"]))

    assert "second" in str(raised.value)
    assert len(reporter.events) == 1
    assert reporter.events[0].capability == "embedding"
    assert reporter.events[0].operation == "embed"
    assert [attempt.provider for attempt in reporter.events[0].attempts] == [
        "primary",
        "backup",
    ]


def test_web_authentication_failure_fails_over_to_backup() -> None:
    reporter = _RecordingReporter()
    primary = _FakeWebClient(error=WebProviderAuthenticationError("tavily", 401))
    backup = _FakeWebClient()
    client = FallbackWebClient(
        [("tavily", primary), ("exa", backup)],
        capability="web_search",
        reporter=reporter.report,
    )
    assert client.provider == "tavily"
    assert client.configured is True

    result = _run(
        client.search(
            "query",
            max_results=1,
            search_depth="basic",
            include_domains=[],
            exclude_domains=[],
        )
    )

    assert result == {"kind": "search", "provider": "tavily"}
    assert primary.search_calls == 1
    assert backup.search_calls == 1
    assert reporter.events == []


def test_web_fetch_all_fail_reports_once() -> None:
    reporter = _RecordingReporter()
    primary = _FakeWebClient(error=WebProviderError("first"))
    backup = _FakeWebClient(error=WebProviderError("second"))
    client = FallbackWebClient(
        [("tavily", primary), ("exa", backup)],
        capability="web_fetch",
        reporter=reporter.report,
    )

    with pytest.raises(WebProviderError):
        _run(client.fetch("https://example.com", max_chars=100))

    assert len(reporter.events) == 1
    event = reporter.events[0]
    assert event.capability == "web_fetch"
    assert event.operation == "fetch"
    assert [attempt.provider for attempt in event.attempts] == ["tavily", "exa"]


def test_notice_attempt_shape_is_stable() -> None:
    attempt = ProviderAttempt(
        provider="tavily",
        status_code=401,
        error_code="authentication_error",
        detail="rejected",
    )
    assert attempt.provider == "tavily"
