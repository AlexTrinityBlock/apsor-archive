"""Tavily search/extract client.

This is the only module that knows Tavily's HTTP contract. The API key travels
in the ``Authorization: Bearer`` header only: it is never placed in the JSON
payload, never logged, and any echo of it in a provider error body is redacted
before the message becomes a domain error.

Response bodies are streamed with a hard byte cap (2 MB search / 5 MB extract)
so a compromised or misbehaving provider cannot exhaust process memory.
"""

import json
import time
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx

from app.module.web_research.exception.domain_error import (
    WebProviderAuthenticationError,
    WebProviderError,
)
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchHit,
    WebSearchResponse,
)
from app.shared.time import utcnow

DEFAULT_BASE_URL = "https://api.tavily.com"
SEARCH_RESPONSE_LIMIT_BYTES = 2 * 1024 * 1024
EXTRACT_RESPONSE_LIMIT_BYTES = 5 * 1024 * 1024
_SEARCH_CONTENT_CHARS = 8_000
_TITLE_CHARS = 500
_ERROR_DETAIL_CHARS = 300
_ERROR_BODY_LIMIT_BYTES = 4_096


class TavilyWebClient:
    """A search and fetch client for one Tavily deployment."""

    provider = "tavily"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None = None,
        timeout_seconds: float = 25.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.configured = bool(self._api_key)

    @property
    def _headers(self) -> dict[str, str]:
        # The key only ever goes in a header; neither the payload nor the query
        # string carries credentials.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> WebSearchResponse:
        if not self.configured:
            raise WebProviderError("Tavily API key is not configured.")
        payload: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
        }
        started = time.perf_counter()
        body = await self._post("/search", payload, SEARCH_RESPONSE_LIMIT_BYTES)
        elapsed_ms = _elapsed_ms(started)
        results, truncated = _parse_search_results(body.get("results"), max_results)
        return WebSearchResponse(
            provider=self.provider,
            query=query,
            results=results,
            elapsed_ms=elapsed_ms,
            truncated=truncated,
            cached=False,
            retrieved_at=utcnow(),
        )

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        # ``max_chars`` is used by WebResearchService for the full-text cache limit
        # and for slicing, and is not applied here; the client always returns the
        # provider's full content so there is a single source for slicing and the
        # truncated semantics.
        del max_chars
        if not self.configured:
            raise WebProviderError("Tavily API key is not configured.")
        payload: dict[str, Any] = {
            "urls": [url],
            "extract_depth": "basic",
            "format": "markdown",
        }
        started = time.perf_counter()
        body = await self._post("/extract", payload, EXTRACT_RESPONSE_LIMIT_BYTES)
        elapsed_ms = _elapsed_ms(started)
        content, resolved_url = _parse_extract_result(body, url)
        return WebFetchResponse(
            provider=self.provider,
            url=resolved_url,
            content=content,
            elapsed_ms=elapsed_ms,
            truncated=False,
            cached=False,
            retrieved_at=utcnow(),
        )

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        limit_bytes: int,
    ) -> dict[str, Any]:
        raw = b""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}{path}",
                    headers=self._headers,
                    json=payload,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise WebProviderAuthenticationError(self.provider, response.status_code)
                    if response.status_code >= 400:
                        # Keep only the redacted, truncated snippet; the error envelope
                        # must never carry headers or keys.
                        body = await self._read_capped(response, _ERROR_BODY_LIMIT_BYTES)
                        detail = self._redact(body.decode("utf-8", errors="replace"))
                        raise WebProviderError(f"HTTP {response.status_code}: {detail}".strip())
                    raw = await self._read_capped(response, limit_bytes)
        except httpx.TimeoutException as exc:
            raise WebProviderError("request timed out") from exc
        except httpx.HTTPError as exc:
            # httpx exception strings can contain the URL or proxy details, so they
            # are always replaced with a fixed message.
            raise WebProviderError("network error") from exc

        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebProviderError("malformed JSON response") from exc
        if not isinstance(parsed, dict):
            raise WebProviderError("malformed JSON response")
        return cast("dict[str, Any]", parsed)

    async def _read_capped(self, response: httpx.Response, limit: int) -> bytes:
        """Read at most ``limit`` bytes, failing the request on overflow.

        Checking Content-Length first is only an optimisation for failing early;
        the real limit is enforced by counting the streamed bytes, because a
        provider can omit or misreport Content-Length.
        """
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    raise WebProviderError("response too large")
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise WebProviderError("response too large")
            chunks.append(chunk)
        return b"".join(chunks)

    def _redact(self, text: str) -> str:
        cleaned = " ".join(text.split())
        if self._api_key:
            cleaned = cleaned.replace(self._api_key, "***")
        return cleaned[:_ERROR_DETAIL_CHARS]


def _parse_search_results(
    raw: object,
    max_results: int,
) -> tuple[list[WebSearchHit], bool]:
    if not isinstance(raw, list):
        raise WebProviderError("malformed search response")
    hits: list[WebSearchHit] = []
    truncated = len(raw) > max_results
    for item in raw[:max_results]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not _is_http_url(url.strip()):
            # Only return citable http(s) results, so provider content such as
            # javascript:/file: never reaches the agent XML or a frontend link.
            continue
        title = item.get("title")
        content = item.get("content")
        text = content if isinstance(content, str) else ""
        if len(text) > _SEARCH_CONTENT_CHARS:
            text = text[:_SEARCH_CONTENT_CHARS]
            truncated = True
        score = _as_score(item.get("score"))
        hits.append(
            WebSearchHit(
                title=(title if isinstance(title, str) else "").strip()[:_TITLE_CHARS],
                url=url.strip(),
                content=text,
                score=score,
            )
        )
    return hits, truncated


def _parse_extract_result(body: dict[str, Any], requested_url: str) -> tuple[str, str]:
    raw_results = body.get("results")
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            content = item.get("raw_content")
            if not isinstance(content, str) or not content.strip():
                content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            url = item.get("url")
            resolved = url.strip() if isinstance(url, str) and url.strip() else requested_url
            return content, resolved
    detail = _failed_result_detail(body.get("failed_results"))
    raise WebProviderError(detail or "the page produced no extractable text")


def _failed_result_detail(raw: object) -> str:
    if not isinstance(raw, list):
        return ""
    for item in raw:
        if not isinstance(item, dict):
            continue
        error = item.get("error")
        if isinstance(error, str) and error.strip():
            return " ".join(error.split())[:_ERROR_DETAIL_CHARS]
    return ""


def _is_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)


def _as_score(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return float(raw)


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1_000))
