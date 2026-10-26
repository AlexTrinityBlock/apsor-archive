"""Web research page pagination: full-document cache and server-defined pages.

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
DEFAULT_FETCH_MAX_CHARS = 20_000
PAGE_BUDGET = 12_000


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
    fetch_max_chars: int = DEFAULT_FETCH_MAX_CHARS,
) -> tuple[WebResearchService, FakeWebCache, FakeFetchClient]:
    cache = FakeWebCache()
    client = FakeFetchClient(content, provider_truncated=provider_truncated)
    service = WebResearchService(
        search_config=FakeWebProviderConfig(capability="web_search"),
        fetch_config=FakeWebProviderConfig(capability="web_fetch"),
        search_client=FakeSearchClient(),
        fetch_client=client,
        cache=cache,
        fetch_max_chars=fetch_max_chars,
    )
    return service, cache, client


def _document(lines: int) -> str:
    """Build a deterministic multi-line document well under the wrap width."""
    return "\n".join(f"line {index:04d} payload" for index in range(1, lines + 1))


async def _read_all_pages(service: WebResearchService) -> list[WebFetchResponse]:
    """Walk pages 1..N and assert every continuation link is exact."""
    responses: list[WebFetchResponse] = []
    page = 1
    while True:
        response = await service.fetch(URL, page=page)
        responses.append(response)
        if not response.has_more:
            return responses
        assert response.next_page == page + 1
        page = response.next_page


def test_fetch_paginates_full_document_with_one_provider_call() -> None:
    document = _document(1_000)
    service, cache, client = _service(document)

    responses = asyncio.run(_read_all_pages(service))

    assert len(responses) == 2
    assert "\n".join(response.content for response in responses) == document
    for index, response in enumerate(responses):
        assert response.page == index + 1
        assert response.total_pages == len(responses)
        assert response.total_chars == len(document)
        assert response.page_chars == len(response.content)
        assert response.page_chars <= PAGE_BUDGET
        assert response.source_truncated is False
        assert response.cached is (index > 0)
        if response.has_more:
            assert response.next_page == response.page + 1
            assert response.truncated is True
        else:
            assert response.next_page is None
            assert response.truncated is False

    # The full document is fetched once and every later page comes from cache.
    assert client.calls == [(URL, 2_000_000)]
    assert cache.ttls == [3_600]
    assert len(cache.values) == 1


def test_single_long_line_is_hard_wrapped_into_contiguous_pages() -> None:
    document = "a" * 30_000
    service, _cache, _client = _service(document)

    responses = asyncio.run(_read_all_pages(service))
    wrapped = "\n".join(response.content for response in responses)
    expected_lines = [
        document[start : start + 800] for start in range(0, len(document), 800)
    ]
    expected = "\n".join(expected_lines)

    assert len(responses) > 1
    assert wrapped == expected
    assert "".join(wrapped.split("\n")) == document
    for response in responses:
        assert response.page_chars <= PAGE_BUDGET
        assert all(len(line) <= 800 for line in response.content.split("\n"))
    assert responses[-1].total_pages == len(responses)
    assert responses[-1].total_chars == len(expected)
    assert responses[-1].has_more is False
    assert responses[-1].next_page is None
    assert responses[-1].truncated is False


def test_web_fetch_args_expose_only_url_and_page() -> None:
    schema = WebFetchArgs.model_json_schema()
    assert list(schema["properties"]) == ["url", "page"]
    assert schema["required"] == ["url"]

    parsed = WebFetchArgs(url=URL)
    assert parsed.page == 1
    assert parsed.offset is None
    assert parsed.limit is None
    assert parsed.max_chars is None
    assert WebFetchArgs(url=URL, page=2).page == 2
    # Legacy fields stay accepted for conversations frozen on v4/v5.
    assert WebFetchArgs(url=URL, offset=5).offset == 5
    assert WebFetchArgs(url=URL, max_chars=4_000).max_chars == 4_000

    with pytest.raises(ValidationError, match=r"Use either offset or page, not both\."):
        WebFetchArgs(url=URL, page=2, offset=5)
    with pytest.raises(ValidationError):
        WebFetchArgs(url=URL, page=0)
    for arguments in (
        {"offset": 0},
        {"limit": 0},
        {"limit": 2_001},
    ):
        with pytest.raises(ValidationError):
            WebFetchArgs(url=URL, **arguments)


def test_legacy_null_page_is_treated_as_omitted() -> None:
    """A frozen v5 payload may send page=null together with offset."""
    parsed = WebFetchArgs(url=URL, page=None, offset=5)
    assert parsed.page == 1
    assert parsed.offset == 5
    assert "page" not in parsed.model_fields_set


def test_tiny_fetch_max_still_fits_one_wrapped_line() -> None:
    """The page budget never drops below one 800-character wrapped line."""
    service, _cache, _client = _service("x" * 2_500, fetch_max_chars=500)

    first = asyncio.run(service.fetch(URL, page=1))

    assert first.page == 1
    assert first.total_pages == 4
    assert first.page_chars == 800
    assert first.page_chars <= 801
    assert first.has_more is True
    assert first.next_page == 2


def test_legacy_offset_maps_to_the_containing_page() -> None:
    document = _document(300)
    service, _cache, _client = _service(document, fetch_max_chars=1_000)

    async def read_by_offset() -> tuple[
        WebFetchResponse, WebFetchResponse, WebFetchResponse, WebFetchResponse
    ]:
        by_offset = await service.fetch(URL, offset=60)
        by_page = await service.fetch(URL, page=2)
        first_page = await service.fetch(URL, page=1)
        past_end = await service.fetch(URL, offset=10_000)
        return by_offset, by_page, first_page, past_end

    by_offset, by_page, first_page, past_end = asyncio.run(read_by_offset())

    assert by_offset.page == 2
    assert by_offset.content == by_page.content
    # The page starts at its own boundary, not at the requested line.
    assert by_offset.content.split("\n")[0] == "line 0056 payload"
    assert first_page.content.split("\n")[0] == "line 0001 payload"
    assert by_offset.page_chars == len(by_offset.content)
    assert by_offset.page_chars <= 1_000
    assert by_offset.has_more is True
    assert by_offset.next_page == 3
    assert by_offset.cached is False
    assert by_page.cached is True

    assert past_end.content == ""
    assert past_end.page == past_end.total_pages + 1
    assert past_end.page_chars == 0
    assert past_end.has_more is False
    assert past_end.next_page is None
    assert past_end.total_pages > 1
    assert past_end.total_chars == len(document)
    assert past_end.truncated is False


def test_out_of_range_page_returns_empty_page_with_real_totals() -> None:
    document = _document(100)
    service, _cache, _client = _service(document)

    response = asyncio.run(service.fetch(URL, page=99))

    assert response.page == 99
    assert response.content == ""
    assert response.page_chars == 0
    assert response.has_more is False
    assert response.next_page is None
    assert response.truncated is False
    assert response.total_pages == 1
    assert response.total_chars == len(document)
    assert response.source_truncated is False


def test_source_cache_cap_sets_source_truncated_on_last_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_research_service, "_MAX_FETCH_CACHE_CHARS", 12_000)
    document = _document(1_000)
    # A 1,000-character page budget keeps multiple pages inside the 12,000-char
    # capped source, so the final page can report the source truncation.
    service, _cache, client = _service(document, fetch_max_chars=1_000)

    responses = asyncio.run(_read_all_pages(service))

    assert len(document) > 12_000
    assert len(responses) > 1
    assert all(response.source_truncated is True for response in responses)
    assert all(response.page_chars <= 1_000 for response in responses)
    assert responses[-1].has_more is False
    assert responses[-1].truncated is True
    assert responses[-1].total_chars == 12_000
    assert "\n".join(response.content for response in responses) == document[:12_000]
    assert client.calls == [(URL, 12_000)]


def test_empty_content_raises_web_provider_error() -> None:
    for content in ("", "   ", " \n\t\r\n "):
        service, cache, _client = _service(content)

        with pytest.raises(WebProviderError, match="no extractable text"):
            asyncio.run(service.fetch(URL))

        assert cache.values == {}


def test_cache_hit_does_not_require_a_configured_provider() -> None:
    document = _document(1_000)
    service, _cache, client = _service(document)

    async def read_after_losing_credentials() -> tuple[WebFetchResponse, WebFetchResponse]:
        first = await service.fetch(URL, page=1)
        client.configured = False
        second = await service.fetch(URL, page=2)
        return first, second

    first, second = asyncio.run(read_after_losing_credentials())

    assert first.cached is False
    assert first.has_more is True
    assert second.cached is True
    assert second.page == 2
    assert second.has_more is False
    assert second.content.startswith(document.split("\n")[len(first.content.split("\n"))])
    assert len(client.calls) == 1
