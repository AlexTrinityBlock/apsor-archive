"""Web research pagination: full-document cache and line slices.

Every collaborator here is an in-memory fake. No Tavily, HTTP, or live archive
database is contacted.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import pytest
from pydantic import ValidationError

from app.module.agent.domain.tool_args import WebFetchArgs
from app.module.web_research.exception.domain_error import WebProviderError
from app.module.web_research.protocol.web_cache_protocol import JsonValue
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchResponse,
)
from app.module.web_research.service import web_research_service
from app.module.web_research.service.web_research_service import WebResearchService

URL = "https://example.com/guide"
RETRIEVED_AT = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FakeWebProviderConfig:
    """Structurally satisfies ``WebProviderConfigProtocol``."""

    capability: str
    provider: str = "tavily"
    base_url: str | None = None
    api_key: str | None = "test"
    enabled: bool = True
    source: str = "test"


class FakeWebCache:
    """JSON-shaped cache with a provider version and recorded writes."""

    def __init__(self, version: int = 7) -> None:
        self.version = version
        self.values: dict[str, JsonValue] = {}
        self.ttls: list[int] = []

    async def get_json(self, key: str) -> JsonValue | None:
        return self.values.get(key)

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttls.append(ttl_seconds)

    async def get_version(self, scope: str = "index") -> int:
        del scope
        return self.version


class FakeFetchClient:
    """Return one preset document and count provider calls."""

    provider = "tavily"
    configured = True

    def __init__(self, content: str, *, provider_truncated: bool = False) -> None:
        self.content = content
        self.provider_truncated = provider_truncated
        self.calls: list[tuple[str, int]] = []

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        self.calls.append((url, max_chars))
        return WebFetchResponse(
            provider=self.provider,
            url=url,
            content=self.content,
            elapsed_ms=12,
            truncated=self.provider_truncated,
            cached=False,
            retrieved_at=RETRIEVED_AT,
        )


class FakeSearchClient:
    """The fetch tests must never touch the search capability."""

    provider = "tavily"
    configured = True

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> WebSearchResponse:
        del query, max_results, search_depth, include_domains, exclude_domains
        raise AssertionError("search must not be called by web fetch tests")


def _service(
    content: str,
    *,
    provider_truncated: bool = False,
) -> tuple[WebResearchService, FakeWebCache, FakeFetchClient]:
    cache = FakeWebCache()
    client = FakeFetchClient(content, provider_truncated=provider_truncated)
    service = WebResearchService(
        search_config=FakeWebProviderConfig(capability="web_search"),
        fetch_config=FakeWebProviderConfig(capability="web_fetch"),
        search_client=FakeSearchClient(),
        fetch_client=client,
        cache=cache,
    )
    return service, cache, client


def _document(lines: int) -> str:
    """Build a deterministic multi-line document well under the wrap width."""
    return "\n".join(f"line {index:04d} payload" for index in range(1, lines + 1))


def test_fetch_paginates_full_document_with_one_provider_call() -> None:
    document = _document(1_000)
    service, cache, client = _service(document)

    async def read_every_page() -> list[WebFetchResponse]:
        responses: list[WebFetchResponse] = []
        offset = 1
        while True:
            response = await service.fetch(
                URL,
                max_chars=2_000,
                offset=offset,
                limit=200,
            )
            responses.append(response)
            if not response.has_more:
                return responses
            assert response.next_offset is not None
            offset = response.next_offset

    responses = asyncio.run(read_every_page())

    assert len(responses) > 1
    assert "\n".join(response.content for response in responses) == document
    seen: list[str] = []
    expected_offset = 1
    total_lines = len(document.split("\n"))
    for index, response in enumerate(responses):
        lines = response.content.split("\n")
        assert response.returned_lines == len(lines)
        assert response.total_lines == total_lines
        assert response.total_pages == 5
        assert response.limit == 200
        assert response.offset == expected_offset
        assert response.page == (response.offset - 1) // response.limit + 1
        assert response.total_chars == len(document)
        assert response.source_truncated is False
        if index == 0:
            assert response.cached is False
        else:
            assert response.cached is True
        aligned_next_page = (
            response.has_more and response.next_offset == response.page * response.limit + 1
        )
        assert response.next_page == (response.page + 1 if aligned_next_page else None)
        if response.has_more:
            assert response.next_offset == response.offset + response.returned_lines
            assert response.truncated is True
        else:
            assert response.next_offset is None
            assert response.next_page is None
            assert response.truncated is False
        seen.extend(lines)
        expected_offset += response.returned_lines

    assert seen == document.split("\n")
    assert len(set(seen)) == total_lines
    # The full document is fetched once and sliced from cache afterwards.
    assert client.calls == [(URL, 2_000_000)]
    assert cache.ttls == [3_600]
    assert len(cache.values) == 1


def test_page_mode_starts_at_the_same_line_as_offset() -> None:
    document = _document(300)
    service, _cache, _client = _service(document)

    async def compare() -> tuple[WebFetchResponse, WebFetchResponse]:
        by_page = await service.fetch(URL, max_chars=20_000, limit=50, page=2)
        by_offset = await service.fetch(URL, max_chars=20_000, limit=50, offset=51)
        return by_page, by_offset

    by_page, by_offset = asyncio.run(compare())

    assert by_page.content == by_offset.content
    assert by_page.offset == 51
    assert by_page.page == 2
    assert by_page.total_pages == 6
    assert by_page.content.split("\n")[0] == "line 0051 payload"
    assert by_page.cached is False
    assert by_offset.cached is True


def test_web_fetch_args_accept_page_alone_and_reject_two_starts() -> None:
    parsed = WebFetchArgs(url=URL, page=2)
    assert parsed.page == 2
    assert parsed.offset == 1
    assert parsed.limit == 200

    with pytest.raises(ValidationError, match=r"Use either offset or page, not both\."):
        WebFetchArgs(url=URL, offset=1, page=2)

    for arguments in (
        {"offset": 0},
        {"limit": 0},
        {"limit": 2_001},
        {"page": 0},
    ):
        with pytest.raises(ValidationError):
            WebFetchArgs(url=URL, **arguments)


def test_out_of_range_offset_and_page_return_empty_slices() -> None:
    document = _document(100)
    service, _cache, _client = _service(document)

    async def read_past_the_end() -> tuple[WebFetchResponse, WebFetchResponse]:
        by_offset = await service.fetch(URL, max_chars=12_000, offset=10_000, limit=200)
        by_page = await service.fetch(URL, max_chars=12_000, page=99, limit=200)
        return by_offset, by_page

    by_offset, by_page = asyncio.run(read_past_the_end())

    for response in (by_offset, by_page):
        assert response.content == ""
        assert response.returned_lines == 0
        assert response.has_more is False
        assert response.next_offset is None
        assert response.next_page is None
        assert response.total_lines == 100
        assert response.total_pages == 1
        assert response.truncated is False

    assert by_offset.offset == 10_000
    assert by_offset.page == 50
    assert by_page.offset == 19_601
    assert by_page.page == 99


def test_long_line_wrapping_preserves_every_character() -> None:
    document = "a" * 2_500
    service, _cache, _client = _service(document)

    async def read_wrapped_lines() -> list[WebFetchResponse]:
        responses: list[WebFetchResponse] = []
        offset = 1
        while True:
            response = await service.fetch(URL, max_chars=1_000, offset=offset, limit=10)
            responses.append(response)
            if not response.has_more:
                return responses
            assert response.next_offset is not None
            offset = response.next_offset

    responses = asyncio.run(read_wrapped_lines())
    wrapped = "\n".join(response.content for response in responses)

    assert len(responses) == 3
    assert [len(line) for line in wrapped.split("\n")] == [800, 800, 800, 100]
    assert "".join(wrapped.split("\n")) == document
    assert responses[-1].returned_lines == 2
    assert responses[-1].total_lines == 4
    assert responses[-1].total_chars == 2_503
    assert responses[-1].truncated is False


def test_source_cache_cap_sets_source_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_research_service, "_MAX_FETCH_CACHE_CHARS", 100)
    document = "\n".join(["x" * 40, "y" * 40, "z" * 40])
    service, _cache, _client = _service(document)

    async def read_capped_source() -> WebFetchResponse:
        return await service.fetch(URL, max_chars=12_000)

    response = asyncio.run(read_capped_source())

    assert response.source_truncated is True
    assert response.truncated is True
    assert response.has_more is False
    assert response.total_lines == 3
    assert response.total_chars == 100
    assert response.content.endswith("z" * 18)


def test_empty_content_raises_web_provider_error() -> None:
    for content in ("", "   ", " \n\t\r\n "):
        service, cache, _client = _service(content)

        with pytest.raises(WebProviderError, match="no extractable text"):
            asyncio.run(service.fetch(URL, max_chars=12_000))

        assert cache.values == {}


def test_cache_hit_does_not_require_a_configured_provider() -> None:
    document = _document(10)
    service, _cache, client = _service(document)

    async def read_after_losing_credentials() -> tuple[WebFetchResponse, WebFetchResponse]:
        first = await service.fetch(URL, max_chars=12_000, limit=5)
        client.configured = False
        second = await service.fetch(URL, max_chars=12_000, limit=5, offset=6)
        return first, second

    first, second = asyncio.run(read_after_losing_credentials())

    assert first.cached is False
    assert second.cached is True
    assert second.offset == 6
    assert len(client.calls) == 1
