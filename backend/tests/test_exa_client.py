"""Exa adapter shape tests: recommended search payload and contents statuses.

These tests never contact Exa. They pin the request fields the skill considers
canonical and the response fields the agent tool needs.
"""

import pytest

from app.infrastructure.web.exa_client import (
    ExaWebClient,
    _parse_contents_result,
    _parse_search_results,
    _search_payload,
)
from app.module.agent.domain.tool_catalog import tool_definitions
from app.module.web_research.exception.domain_error import WebProviderError


def test_exa_search_payload_uses_objective_and_highlights() -> None:
    payload = _search_payload(
        query="latest battery recycling policy",
        max_results=5,
        include_domains=["https://Example.com/News"],
        exclude_domains=[],
        objective="Prefer official EU sources; pull the effective dates.",
    )

    assert payload["query"] == "latest battery recycling policy"
    assert payload["type"] == "auto"
    assert payload["contents"] == {"highlights": True}
    assert payload["objective"] == "Prefer official EU sources; pull the effective dates."
    assert payload["numResults"] == 5
    assert payload["includeDomains"] == ["example.com/news"]
    assert "excludeDomains" not in payload
    assert "maxAgeHours" not in payload
    assert "category" not in payload


def test_exa_search_payload_omits_default_result_count() -> None:
    payload = _search_payload(
        query="query",
        max_results=10,
        include_domains=[],
        exclude_domains=[],
        objective="",
    )

    assert "numResults" not in payload
    assert "objective" not in payload


def test_exa_search_results_use_highlights_and_optional_score() -> None:
    hits, truncated = _parse_search_results(
        {
            "results": [
                {
                    "title": "Primary source",
                    "url": "https://example.com/source",
                    "highlights": ["First passage.", "Second passage."],
                    "score": 0.91,
                },
                {
                    "title": "No content",
                    "url": "https://example.com/empty",
                    "highlights": [],
                    "score": None,
                },
                {
                    "title": "Unsafe",
                    "url": "javascript:alert(1)",
                    "highlights": ["ignored"],
                },
            ]
        },
        max_results=5,
    )

    assert len(hits) == 2
    assert hits[0].url == "https://example.com/source"
    assert hits[0].content == "First passage.\n\nSecond passage."
    assert hits[0].score == 0.91
    assert hits[1].content == ""
    assert hits[1].score is None
    assert truncated is False


def test_exa_search_marks_provider_truncation_only_when_over_limit() -> None:
    _hits, truncated = _parse_search_results(
        {"results": [{"url": "https://example.com/a", "highlights": ["x"]}] * 3},
        max_results=2,
    )
    assert truncated is True


def test_exa_contents_returns_full_text_and_resolved_url() -> None:
    content, resolved, truncated = _parse_contents_result(
        {
            "results": [
                {
                    "url": "https://example.com/final",
                    "text": "# Article\n\nBody text.",
                }
            ],
            "statuses": [
                {"id": "https://example.com/final", "status": "success", "source": "crawled"}
            ],
        },
        requested_url="https://example.com/original",
        max_characters=100,
    )

    assert content == "# Article\n\nBody text."
    assert resolved == "https://example.com/final"
    assert truncated is False


def test_exa_contents_surfaces_object_status_error() -> None:
    with pytest.raises(WebProviderError, match="CRAWL_TIMEOUT"):
        _parse_contents_result(
            {
                "results": [],
                "statuses": [
                    {
                        "id": "https://example.com/slow",
                        "status": "error",
                        "error": {"tag": "CRAWL_TIMEOUT", "httpStatusCode": 504},
                    }
                ],
            },
            requested_url="https://example.com/slow",
            max_characters=100,
        )


def test_exa_client_is_disabled_without_a_key() -> None:
    client = ExaWebClient(api_key="")

    assert client.configured is False
    assert client.provider == "exa"


def test_web_search_tool_requires_objective_in_the_new_schema() -> None:
    search = next(
        definition
        for definition in tool_definitions()
        if definition["function"]["name"] == "web_search"
    )
    parameters = search["function"]["parameters"]

    assert parameters["required"] == ["query", "objective"]
    assert parameters["properties"]["objective"]["description"] == (
        "Goal for this search turn; say which documents should rank first, "
        "which should be excluded, and what specific facts or figures to pull "
        "from them."
    )
