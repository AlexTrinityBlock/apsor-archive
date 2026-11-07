"""Exa search and contents client.

The web-research slice owns this adapter. Exa accepts either ``x-api-key`` or
``Authorization: Bearer``; the key is sent in the ``x-api-key`` header and never
placed in the payload or a URL. Response bodies are streamed with a hard byte
cap so a misbehaving provider cannot exhaust process memory.

Search follows Exa's recommended request shape: a natural-language query,
``type="auto"``, and ``contents={"highlights": true}``. The optional
``objective`` is the goal the search serves; it is forwarded unchanged and is
never logged. Contents is the known-URL extraction path and requests the full
rendered text with a fresh crawl.
"""

import hashlib
import json
import logging
import time
from typing import Any, Literal
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

DEFAULT_BASE_URL = "https://api.exa.ai"
SEARCH_RESPONSE_LIMIT_BYTES = 2 * 1024 * 1024
CONTENTS_RESPONSE_LIMIT_BYTES = 5 * 1024 * 1024
_ERROR_BODY_LIMIT_BYTES = 4_096
_ERROR_DETAIL_CHARS = 300
_TITLE_CHARS = 500
_MAX_CONTENTS_CHARS = 1_000_000
_LIVE_CRAWL_TIMEOUT_MS = 15_000

logger = logging.getLogger(__name__)


class ExaWebClient:
    """One Exa deployment's search and contents endpoints."""

    provider = "exa"

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
        return {
            "x-api-key": self._api_key,
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
        if not self.configured:
            raise WebProviderError("Exa API key is not configured.")
        # Exa's auto mode is the recommended default. Tavily's basic/advanced
        # hint has no direct Exa equivalent, so it is intentionally accepted and
        # not sent; callers with an explicit latency requirement can add a mode
        # through a future provider-specific control.
        del search_depth
        started = time.perf_counter()
        payload = _search_payload(
            query=query,
            max_results=max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            objective=objective,
        )
        logger.info(
            "exa search started type=auto max_results=%d objective_chars=%d "
            "include_domains=%d exclude_domains=%d",
            max_results,
            len(objective.strip()),
            len(include_domains),
            len(exclude_domains),
        )
        body, status_code, raw_bytes = await self._post(
            "/search",
            payload,
            SEARCH_RESPONSE_LIMIT_BYTES,
        )
        elapsed_ms = _elapsed_ms(started)
        hits, truncated = _parse_search_results(body, max_results)
        logger.info(
            "exa search completed status=%d elapsed_ms=%d results=%d "
            "truncated=%s request_id=%s cost_usd=%s body_bytes=%d",
            status_code,
            elapsed_ms,
            len(hits),
            truncated,
            _request_id(body) or "-",
            _cost(body),
            raw_bytes,
        )
        return WebSearchResponse(
            provider=self.provider,
            query=query,
            results=hits,
            elapsed_ms=elapsed_ms,
            truncated=truncated,
            cached=False,
            retrieved_at=utcnow(),
        )

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        if not self.configured:
            raise WebProviderError("Exa API key is not configured.")
        started = time.perf_counter()
        max_characters = max(1, min(max_chars, _MAX_CONTENTS_CHARS))
        payload: dict[str, Any] = {
            "urls": [url],
            "text": {
                "verbosity": "full",
                "maxCharacters": max_characters,
            },
            "maxAgeHours": 0,
            "livecrawlTimeout": _LIVE_CRAWL_TIMEOUT_MS,
        }
        logger.info(
            "exa contents started max_chars=%d url_hash=%s",
            max_characters,
            _url_digest(url),
        )
        body, status_code, raw_bytes = await self._post(
            "/contents",
            payload,
            CONTENTS_RESPONSE_LIMIT_BYTES,
        )
        elapsed_ms = _elapsed_ms(started)
        content, resolved_url, truncated = _parse_contents_result(
            body,
            requested_url=url,
            max_characters=max_characters,
        )
        logger.info(
            "exa contents completed status=%d elapsed_ms=%d text_chars=%d "
            "truncated=%s request_id=%s cost_usd=%s body_bytes=%d",
            status_code,
            elapsed_ms,
            len(content),
            truncated,
            _request_id(body) or "-",
            _cost(body),
            raw_bytes,
        )
        return WebFetchResponse(
            provider=self.provider,
            url=resolved_url,
            content=content,
            elapsed_ms=elapsed_ms,
            truncated=truncated,
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
                            "exa request failed endpoint=%s status=%d error=auth",
                            path,
                            status_code,
                        )
                        raise WebProviderAuthenticationError(self.provider, status_code)
                    if status_code >= 400:
                        body = await self._read_capped(response, _ERROR_BODY_LIMIT_BYTES)
                        detail = self._redact(body.decode("utf-8", errors="replace"))
                        logger.warning(
                            "exa request failed endpoint=%s status=%d error=%r",
                            path,
                            status_code,
                            detail or "-",
                        )
                        raise WebProviderError(
                            f"HTTP {status_code}: {detail}".strip()
                        )
                    raw = await self._read_capped(response, limit_bytes)
        except httpx.TimeoutException as exc:
            logger.warning("exa request failed endpoint=%s error=timeout", path)
            raise WebProviderError("request timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "exa request failed endpoint=%s error_type=%s",
                path,
                type(exc).__name__,
            )
            raise WebProviderError("network error") from exc

        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "exa response invalid endpoint=%s body_bytes=%d error=malformed_json",
                path,
                len(raw),
            )
            raise WebProviderError("malformed JSON response") from exc
        if not isinstance(parsed, dict):
            logger.warning(
                "exa response invalid endpoint=%s body_bytes=%d error=non_object",
                path,
                len(raw),
            )
            raise WebProviderError("malformed JSON response")
        if parsed.get("error"):
            detail = _error_envelope_detail(parsed)
            logger.warning(
                "exa response error endpoint=%s status=%d error=%r request_id=%s",
                path,
                status_code,
                detail or "-",
                _request_id(parsed) or "-",
            )
            raise WebProviderError(detail or "the provider returned an error")
        return parsed, status_code, len(raw)

    async def _read_capped(self, response: httpx.Response, limit: int) -> bytes:
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


def _search_payload(
    *,
    query: str,
    max_results: int,
    include_domains: list[str],
    exclude_domains: list[str],
    objective: str,
) -> dict[str, Any]:
    """Build the recommended Exa search request without over-specifying it."""
    payload: dict[str, Any] = {
        "query": query,
        "type": "auto",
        "contents": {"highlights": True},
    }
    # Exa's server default is 10. Send a count only when the caller chose a
    # different product limit; the agent tool defaults to five.
    if max_results != 10:
        payload["numResults"] = max_results
    if objective.strip():
        payload["objective"] = objective.strip()
    include = _normalize_domains(include_domains)
    exclude = _normalize_domains(exclude_domains)
    if include:
        payload["includeDomains"] = include
    if exclude:
        payload["excludeDomains"] = exclude
    return payload


def _parse_search_results(
    body: dict[str, Any],
    max_results: int,
) -> tuple[list[WebSearchHit], bool]:
    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        raise WebProviderError("malformed search response")
    hits: list[WebSearchHit] = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not _is_http_url(url.strip()):
            continue
        title = item.get("title")
        hits.append(
            WebSearchHit(
                title=(title if isinstance(title, str) else "").strip()[:_TITLE_CHARS],
                url=url.strip(),
                content=_result_content(item),
                score=_as_score(item.get("score")),
            )
        )
    return hits, len(raw_results) > max_results


def _result_content(item: dict[str, Any]) -> str:
    highlights = item.get("highlights")
    if isinstance(highlights, list):
        parts: list[str] = []
        for value in highlights:
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if parts:
            return "\n\n".join(parts)
    text = item.get("text")
    if isinstance(text, str):
        return text
    return ""


def _parse_contents_result(
    body: dict[str, Any],
    *,
    requested_url: str,
    max_characters: int,
) -> tuple[str, str, bool]:
    raw_results = body.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        detail = _status_detail(body.get("statuses"), requested_url)
        raise WebProviderError(detail or "the page produced no extractable text")
    item = raw_results[0]
    if not isinstance(item, dict):
        raise WebProviderError("malformed contents response")
    content = item.get("text")
    if not isinstance(content, str) or not content.strip():
        detail = _status_detail(body.get("statuses"), requested_url)
        raise WebProviderError(detail or "the page produced no extractable text")
    url = item.get("url")
    resolved = url.strip() if isinstance(url, str) and url.strip() else requested_url
    status_error = _status_detail(body.get("statuses"), resolved)
    if status_error:
        raise WebProviderError(status_error)
    return content, resolved, len(content) >= max_characters


def _status_detail(raw_statuses: object, requested_url: str) -> str:
    if not isinstance(raw_statuses, list):
        return ""
    candidates = [item for item in raw_statuses if isinstance(item, dict)]
    matching = [
        item
        for item in candidates
        if item.get("id") in {requested_url, None}
    ]
    # Exa can key a status by a document id supplied through ``ids``. With a
    # single requested URL the one returned status is still unambiguous.
    if not matching and len(candidates) == 1:
        matching = candidates
    for item in matching:
        status = item.get("status")
        if status == "success":
            return ""
        error = item.get("error")
        if isinstance(error, dict):
            tag = _clip_text(error.get("tag"))
            status_code = error.get("httpStatusCode")
            if tag and isinstance(status_code, int) and not isinstance(status_code, bool):
                return f"Exa contents error: {tag} (HTTP {status_code})"
            if tag:
                return f"Exa contents error: {tag}"
        if isinstance(error, str) and error.strip():
            return " ".join(error.split())[:_ERROR_DETAIL_CHARS]
        if isinstance(status, str) and status.strip():
            return f"Exa contents status: {status.strip()[:_ERROR_DETAIL_CHARS]}"
    return ""


def _error_envelope_detail(body: dict[str, Any]) -> str:
    error = body.get("error")
    tag = body.get("tag")
    parts = [
        value
        for value in (
            _clip_text(tag),
            _clip_text(error),
        )
        if value
    ]
    return f"Exa error ({', '.join(parts)})" if parts else ""


def _request_id(body: dict[str, Any]) -> str | None:
    value = body.get("requestId")
    return value if isinstance(value, str) and value else None


def _cost(body: dict[str, Any]) -> str:
    cost = body.get("costDollars")
    if isinstance(cost, dict):
        total = cost.get("total")
        if isinstance(total, int | float) and not isinstance(total, bool):
            return f"{float(total):.6f}"
    return "-"


def _normalize_domains(domains: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in domains:
        text = value.strip().lower()
        if not text:
            continue
        if "://" in text:
            parts = urlsplit(text)
            host = parts.hostname or ""
            path = parts.path.rstrip("/")
            text = f"{host}{path}" if host else ""
        else:
            text = text.strip("/")
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return cleaned


def _as_score(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return float(raw)


def _clip_text(value: object, limit: int = _ERROR_DETAIL_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _is_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)


def _url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1_000))


__all__ = [
    "CONTENTS_RESPONSE_LIMIT_BYTES",
    "DEFAULT_BASE_URL",
    "SEARCH_RESPONSE_LIMIT_BYTES",
    "ExaWebClient",
]
