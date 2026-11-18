"""DeepSeek web client shape tests.

These tests never contact DeepSeek. They pin the request transformation the
128-character query limit requires and the response fields the agent tool
needs. HTTP failures use ``httpx.MockTransport`` so the real error mapping in
``_post`` is exercised without a network connection.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.infrastructure.web import deepseek_client
from app.infrastructure.web.deepseek_client import (
    MAX_QUERY_CHARS,
    DeepSeekWebClient,
    _build_search_query,
    _parse_fetch_result,
    _parse_search_results,
)
from app.module.web_research.exception.domain_error import (
    WebProviderAuthenticationError,
    WebProviderError,
)

SEARCH_RESPONSE = {
    "results": [
        {
            "rerank_score": 2.5,
            "title": "Primary source",
            "url": "https://example.com/source",
            "snippet": "Short snippet.",
            "summary": "A summary.",
            "content": "Full content.",
            "site_name": "Example",
            "site_icon": None,
            "date": "2026-11-01",
            "authority": 8,
        }
    ]
}


def _search(
    client: DeepSeekWebClient,
    query: str = "test query",
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    objective: str = "",
    search_depth: str = "advanced",
) -> Any:
    return asyncio.run(
        client.search(
            query,
            max_results=max_results,
            search_depth=search_depth,  # type: ignore[arg-type]
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            objective=objective,
        )
    )


def test_client_is_disabled_without_a_key() -> None:
    client = DeepSeekWebClient(api_key="")

    assert client.provider == "deepseek"
    assert client.configured is False


def test_search_payload_uses_count_need_content_and_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DeepSeekWebClient(api_key="test-key")
    captured: dict[str, Any] = {}

    async def fake_post(
        path: str,
        payload: dict[str, Any],
        limit_bytes: int,
    ) -> tuple[dict[str, Any], int, int]:
        captured.update(path=path, payload=payload, limit_bytes=limit_bytes)
        return SEARCH_RESPONSE, 200, 128

    monkeypatch.setattr(client, "_post", fake_post)

    response = _search(
        client,
        "battery recycling policy",
        max_results=25,
        objective="  Prefer official EU sources.  ",
        search_depth="basic",
    )

    assert captured["path"] == "/v1/tools/search"
    payload = captured["payload"]
    assert payload["query"] == "battery recycling policy"
    assert payload["count"] == 10
    assert payload["need_content"] is True
    assert payload["ori_question"] == "Prefer official EU sources."
    assert "search_depth" not in payload
    assert captured["limit_bytes"] == 2 * 1024 * 1024
    assert response.provider == "deepseek"
    assert response.query == "battery recycling policy"
    assert response.results[0].content == "Full content."
    assert response.results[0].score == 2.5


def test_search_count_is_clamped_and_objective_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DeepSeekWebClient(api_key="test-key")
    captured: dict[str, Any] = {}

    async def fake_post(
        path: str,
        payload: dict[str, Any],
        limit_bytes: int,
    ) -> tuple[dict[str, Any], int, int]:
        del path, limit_bytes
        captured.update(payload)
        return {"results": []}, 200, 2

    monkeypatch.setattr(client, "_post", fake_post)

    _search(client, "query", max_results=0, objective="x" * 200)

    assert captured["count"] == 1
    assert len(captured["ori_question"]) == MAX_QUERY_CHARS


def test_search_payload_translates_domains_into_query_operators() -> None:
    query = _build_search_query(
        "latest policy",
        [
            "https://Example.com/News",
            "*.docs.example.org",
            "example.com:8443",
            "",
            "not a domain",
            "example.com",
        ],
        ["spam.example.net", "https://bad.example/"],
    )

    assert query == (
        "latest policy site:example.com OR site:docs.example.org "
        "-site:spam.example.net -site:bad.example"
    )


def test_search_query_is_capped_at_128_characters() -> None:
    query = _build_search_query(
        "word " * 60,
        [],
        [],
    )

    assert len(query) <= MAX_QUERY_CHARS
    assert query.startswith("word")
    assert not query.endswith(" ")


def test_domain_operators_keep_the_query_within_the_cap() -> None:
    query = _build_search_query(
        "latest battery recycling policy " * 10,
        ["example.com", "docs.example.org"],
        ["spam.example.net"],
    )

    assert len(query) <= MAX_QUERY_CHARS
    assert "site:example.com OR site:docs.example.org" in query
    assert "-site:spam.example.net" in query
    # The operators are preserved and only the natural-language part shrinks.
    assert query.endswith("-site:spam.example.net")


def test_oversized_operators_are_dropped_in_favour_of_the_query() -> None:
    long_host = f"{'a' * 63}.{'b' * 63}.{'c' * 50}"
    query = _build_search_query(
        "a useful natural-language query",
        [long_host],
        [],
    )

    assert len(query) <= MAX_QUERY_CHARS
    assert "site:" not in query
    assert query == "a useful natural-language query"


def test_search_results_fall_back_from_content_to_summary_to_snippet() -> None:
    hits, truncated = _parse_search_results(
        [
            {
                "title": "Content",
                "url": "https://example.com/content",
                "content": "Body.",
                "summary": "Summary.",
                "snippet": "Snippet.",
                "rerank_score": 1.75,
            },
            {
                "title": "Summary",
                "url": "https://example.com/summary",
                "content": "   ",
                "summary": "Summary.",
                "snippet": "Snippet.",
            },
            {
                "title": "Snippet",
                "url": "https://example.com/snippet",
                "snippet": "Snippet.",
            },
            {
                "title": "Unsafe",
                "url": "javascript:alert(1)",
                "content": "ignored",
            },
        ],
        max_results=10,
    )

    assert [hit.content for hit in hits] == ["Body.", "Summary.", "Snippet."]
    assert hits[0].score == 1.75
    assert hits[1].score is None
    assert truncated is False


def test_search_results_clip_title_content_and_mark_truncation() -> None:
    hits, truncated = _parse_search_results(
        [
            {
                "title": "t" * 501,
                "url": "https://example.com/long",
                "content": "c" * 9_000,
                "rerank_score": "high",
            }
        ]
        * 3,
        max_results=2,
    )

    assert len(hits) == 2
    assert len(hits[0].title) == 500
    assert len(hits[0].content) == 8_000
    assert hits[0].score is None
    assert truncated is True


def test_search_response_marks_provider_truncation_over_the_limit() -> None:
    _hits, truncated = _parse_search_results(
        [
            {"url": f"https://example.com/{index}", "content": "x"}
            for index in range(3)
        ],
        max_results=2,
    )

    assert truncated is True


def test_malformed_search_results_raise_a_provider_error() -> None:
    with pytest.raises(WebProviderError, match="malformed search response"):
        _parse_search_results({"not": "a list"}, max_results=5)


def test_fetch_payload_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DeepSeekWebClient(api_key="test-key")
    captured: dict[str, Any] = {}

    async def fake_post(
        path: str,
        payload: dict[str, Any],
        limit_bytes: int,
    ) -> tuple[dict[str, Any], int, int]:
        captured.update(path=path, payload=payload, limit_bytes=limit_bytes)
        return {"title": "Example", "content": "# Page\n\nBody"}, 200, 64

    monkeypatch.setattr(client, "_post", fake_post)

    response = asyncio.run(client.fetch("https://example.com/page", max_chars=1_000))

    assert captured["path"] == "/v1/tools/fetch"
    assert captured["payload"] == {"url": "https://example.com/page"}
    assert captured["limit_bytes"] == 5 * 1024 * 1024
    assert response.provider == "deepseek"
    assert response.url == "https://example.com/page"
    assert response.content == "# Page\n\nBody"
    assert response.truncated is False
    assert response.cached is False


@pytest.mark.parametrize("body", [{}, {"content": ""}, {"content": "   \n\t"}])
def test_fetch_empty_content_raises(body: dict[str, Any]) -> None:
    with pytest.raises(WebProviderError, match="no extractable text"):
        _parse_fetch_result(body)


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        del args
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    # ``deepseek_client.httpx`` is the httpx module itself, so this replaces
    # AsyncClient for the duration of the test only.
    monkeypatch.setattr(deepseek_client.httpx, "AsyncClient", factory)


def test_401_maps_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="super-secret-key")

    with pytest.raises(WebProviderAuthenticationError, match=r"HTTP 401"):
        _search(client)


def test_403_maps_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "blocked"}})

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="super-secret-key")

    with pytest.raises(WebProviderAuthenticationError, match=r"HTTP 403"):
        asyncio.run(client.fetch("https://example.com", max_chars=100))


def test_402_keeps_the_provider_balance_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={"error": {"message": "Insufficient Balance"}},
        )

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="super-secret-key")

    with pytest.raises(WebProviderError, match=r"HTTP 402.*Insufficient Balance"):
        _search(client)


def test_error_body_redacts_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "super-secret-key"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=f"bad key {key}")

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key=key)

    with pytest.raises(WebProviderError) as raised:
        _search(client)

    assert key not in str(raised.value)
    assert "***" in str(raised.value)


def test_malformed_json_maps_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="test-key")

    with pytest.raises(WebProviderError, match="malformed JSON response"):
        _search(client)


def test_non_object_json_maps_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(["not", "an", "object"]).encode())

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="test-key")

    with pytest.raises(WebProviderError, match="malformed JSON response"):
        _search(client)


def test_timeout_maps_to_a_fixed_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out at https://user:secret@api.deepseek.com")

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="test-key")

    with pytest.raises(WebProviderError, match="request timed out"):
        _search(client)


def test_streamed_response_over_the_cap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * (deepseek_client.SEARCH_RESPONSE_LIMIT_BYTES + 1),
        )

    _install_transport(monkeypatch, handler)
    client = DeepSeekWebClient(api_key="test-key")

    with pytest.raises(WebProviderError, match="response too large"):
        _search(client)
