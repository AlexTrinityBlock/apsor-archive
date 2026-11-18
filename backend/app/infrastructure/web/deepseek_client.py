"""DeepSeek web search/fetch client.

This is the only module that knows DeepSeek's web-tool HTTP contract. The API
key travels in the ``Authorization: Bearer`` header only: it is never placed in
the JSON payload, never logged, and any echo of it in a provider error body is
redacted before the message becomes a domain error.

DeepSeek exposes no domain filters, so include/exclude domains are translated
into ``site:`` query operators. The search endpoint also hard-caps ``query`` at
128 Unicode characters, which includes those operators; the final query is
always shortened to fit before it leaves the process.

Response bodies are streamed with a hard byte cap (2 MB search / 5 MB fetch)
so a compromised or misbehaving provider cannot exhaust process memory.
"""

import hashlib
import json
import logging
import re
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

DEFAULT_BASE_URL = "https://api.deepseek.com"
SEARCH_RESPONSE_LIMIT_BYTES = 2 * 1024 * 1024
FETCH_RESPONSE_LIMIT_BYTES = 5 * 1024 * 1024
SEARCH_PATH = "/v1/tools/search"
FETCH_PATH = "/v1/tools/fetch"
MAX_QUERY_CHARS = 128
MAX_SEARCH_RESULTS = 10
_SEARCH_CONTENT_CHARS = 8_000
_TITLE_CHARS = 500
_ERROR_DETAIL_CHARS = 300
_ERROR_BODY_LIMIT_BYTES = 4_096
# Hostnames in ``site:`` operators must be bare, lower-case ASCII labels.
_HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST_PATTERN = re.compile(rf"^{_HOST_LABEL}(?:\.{_HOST_LABEL})*$")

logger = logging.getLogger(__name__)


class DeepSeekWebClient:
    """A search and fetch client for one DeepSeek deployment."""

    provider = "deepseek"

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
        objective: str = "",
    ) -> WebSearchResponse:
        # DeepSeek has no basic/advanced depth control; accept the shared
        # argument so the service and the agent tool stay provider-neutral.
        del search_depth
        if not self.configured:
            raise WebProviderError("DeepSeek API key is not configured.")
        final_query = _build_search_query(query, include_domains, exclude_domains)
        count = max(1, min(max_results, MAX_SEARCH_RESULTS))
        payload: dict[str, Any] = {
            "query": final_query,
            "count": count,
            "need_content": True,
        }
        # ``ori_question`` improves ranking when the caller has a goal; the
        # endpoint accepts at most 128 characters like the query.
        ori_question = objective.strip()[:MAX_QUERY_CHARS]
        if ori_question:
            payload["ori_question"] = ori_question
        started = time.perf_counter()
        logger.info(
            "deepseek search started count=%d query_chars=%d objective_chars=%d "
            "include_domains=%d exclude_domains=%d",
            count,
            len(final_query),
            len(ori_question),
            len(include_domains),
            len(exclude_domains),
        )
        body, status_code, body_bytes = await self._post(
            SEARCH_PATH,
            payload,
            SEARCH_RESPONSE_LIMIT_BYTES,
        )
        elapsed_ms = _elapsed_ms(started)
        results, truncated = _parse_search_results(body.get("results"), max_results)
        logger.info(
            "deepseek search completed status=%d elapsed_ms=%d results=%d "
            "truncated=%s body_bytes=%d request_id=%s",
            status_code,
            elapsed_ms,
            len(results),
            truncated,
            body_bytes,
            _request_id(body) or "-",
        )
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
        # ``max_chars`` belongs to WebResearchService's full-text cache and page
        # slicing; the client always returns the provider's complete content so
        # there is one source for slicing and truncation semantics.
        del max_chars
        if not self.configured:
            raise WebProviderError("DeepSeek API key is not configured.")
        payload: dict[str, Any] = {"url": url}
        started = time.perf_counter()
        logger.info("deepseek fetch started url_hash=%s", _url_digest(url))
        body, status_code, body_bytes = await self._post(
            FETCH_PATH,
            payload,
            FETCH_RESPONSE_LIMIT_BYTES,
        )
        elapsed_ms = _elapsed_ms(started)
        content = _parse_fetch_result(body)
        logger.info(
            "deepseek fetch completed status=%d elapsed_ms=%d content_chars=%d "
            "body_bytes=%d request_id=%s url_hash=%s",
            status_code,
            elapsed_ms,
            len(content),
            body_bytes,
            _request_id(body) or "-",
            _url_digest(url),
        )
        return WebFetchResponse(
            provider=self.provider,
            url=url,
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
    ) -> tuple[dict[str, Any], int, int]:
        raw = b""
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}{path}",
                    headers=self._headers,
                    json=payload,
                ) as response:
                    status_code = response.status_code
                    if status_code in {401, 403}:
                        logger.warning(
                            "deepseek request failed endpoint=%s status=%d "
                            "elapsed_ms=%d error=auth",
                            path,
                            status_code,
                            _elapsed_ms(started),
                        )
                        raise WebProviderAuthenticationError(self.provider, status_code)
                    if status_code >= 400:
                        # Keep only the redacted, truncated snippet; the error
                        # envelope must never carry headers or keys.
                        body = await self._read_capped(response, _ERROR_BODY_LIMIT_BYTES)
                        detail = self._redact(body.decode("utf-8", errors="replace"))
                        logger.warning(
                            "deepseek request failed endpoint=%s status=%d "
                            "elapsed_ms=%d detail_chars=%d",
                            path,
                            status_code,
                            _elapsed_ms(started),
                            len(detail),
                        )
                        raise WebProviderError(
                            f"HTTP {status_code}: {detail}".strip()
                        )
                    raw = await self._read_capped(response, limit_bytes)
        except httpx.TimeoutException as exc:
            logger.warning(
                "deepseek request failed endpoint=%s elapsed_ms=%d error=timeout",
                path,
                _elapsed_ms(started),
            )
            raise WebProviderError("request timed out") from exc
        except httpx.HTTPError as exc:
            # httpx exception strings can contain the URL or proxy details, so
            # they are always replaced with a fixed message.
            logger.warning(
                "deepseek request failed endpoint=%s elapsed_ms=%d error_type=%s",
                path,
                _elapsed_ms(started),
                type(exc).__name__,
            )
            raise WebProviderError("network error") from exc

        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "deepseek response invalid endpoint=%s body_bytes=%d error=malformed_json",
                path,
                len(raw),
            )
            raise WebProviderError("malformed JSON response") from exc
        if not isinstance(parsed, dict):
            logger.warning(
                "deepseek response invalid endpoint=%s body_bytes=%d error=non_object",
                path,
                len(raw),
            )
            raise WebProviderError("malformed JSON response")
        return cast("dict[str, Any]", parsed), status_code, len(raw)

    async def _read_capped(self, response: httpx.Response, limit: int) -> bytes:
        """Read at most ``limit`` bytes, failing the request on overflow.

        Checking Content-Length first is only an optimisation for failing early;
        the real limit is enforced by counting the streamed bytes because a
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


def _build_search_query(
    query: str,
    include_domains: list[str],
    exclude_domains: list[str],
) -> str:
    """Return a query that keeps DeepSeek's 128-character limit.

    Domain filters become ``site:`` operators because the search endpoint has
    no separate domain fields. The operators are kept intact while the base
    query is shortened at a word boundary; when the operators alone would
    consume the whole budget, the lowest-priority domains are dropped first.
    """
    base = " ".join(query.split())
    include_hosts = _normalize_hosts(include_domains)
    exclude_hosts = _normalize_hosts(exclude_domains)

    suffix = _operator_suffix(include_hosts, exclude_hosts)
    if not suffix:
        return _truncate_at_word(base, MAX_QUERY_CHARS)

    # Drop trailing domains only when the operators cannot leave room for any
    # part of the natural-language query.
    while suffix and len(suffix) > MAX_QUERY_CHARS - 1:
        if exclude_hosts:
            exclude_hosts.pop()
        elif include_hosts:
            include_hosts.pop()
        else:  # pragma: no cover - the loop empties both lists first.
            break
        suffix = _operator_suffix(include_hosts, exclude_hosts)

    if not suffix:
        return _truncate_at_word(base, MAX_QUERY_CHARS)
    budget = MAX_QUERY_CHARS - len(suffix) - 1
    shortened = _truncate_at_word(base, budget)
    return f"{shortened} {suffix}" if shortened else suffix


def _operator_suffix(include_hosts: list[str], exclude_hosts: list[str]) -> str:
    include = ""
    if include_hosts:
        terms = [f"site:{host}" for host in include_hosts]
        include = " OR ".join(terms)
    exclude = " ".join(f"-site:{host}" for host in exclude_hosts)
    return " ".join(part for part in (include, exclude) if part)


def _normalize_hosts(domains: list[str]) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for value in domains:
        host = _normalize_host(value)
        if host and host not in seen:
            seen.add(host)
            hosts.append(host)
    return hosts


def _normalize_host(value: str) -> str:
    """Reduce one domain entry to a bare lower-case hostname."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        try:
            parts = urlsplit(text)
        except ValueError:
            return ""
        host = parts.hostname or ""
    else:
        host = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if "@" in host:
            return ""
        # IPv6 literals are never useful as ``site:`` filters.
        if host.startswith("["):
            return ""
        if ":" in host:
            host = host.rsplit(":", 1)[0]
    host = host.strip().strip(".").lstrip("*.")
    if not host:
        return ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    if len(host) > 253 or not _HOST_PATTERN.fullmatch(host):
        return ""
    return host


def _truncate_at_word(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    head = text[:limit]
    boundary = head.rfind(" ")
    # Only cut at a word boundary when it does not discard most of the budget.
    if boundary >= limit // 2:
        head = head[:boundary]
    return head.rstrip()


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
        content = _result_content(item)
        if len(content) > _SEARCH_CONTENT_CHARS:
            content = content[:_SEARCH_CONTENT_CHARS]
            truncated = True
        title = item.get("title")
        hits.append(
            WebSearchHit(
                title=(title if isinstance(title, str) else "").strip()[:_TITLE_CHARS],
                url=url.strip(),
                content=content,
                score=_as_score(item.get("rerank_score")),
            )
        )
    return hits, truncated


def _result_content(item: dict[str, Any]) -> str:
    # ``need_content`` usually fills ``content``; summary and snippet are the
    # documented fallbacks when the page body is unavailable.
    for key in ("content", "summary", "snippet"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _parse_fetch_result(body: dict[str, Any]) -> str:
    content = body.get("content")
    if not isinstance(content, str) or not content.strip():
        raise WebProviderError("the page produced no extractable text")
    return content


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


def _request_id(body: dict[str, Any]) -> str | None:
    for key in ("request_id", "id"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return " ".join(value.split())[:128]
    return None


def _url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1_000))


__all__ = [
    "DEFAULT_BASE_URL",
    "FETCH_PATH",
    "FETCH_RESPONSE_LIMIT_BYTES",
    "MAX_QUERY_CHARS",
    "MAX_SEARCH_RESULTS",
    "SEARCH_PATH",
    "SEARCH_RESPONSE_LIMIT_BYTES",
    "DeepSeekWebClient",
]
