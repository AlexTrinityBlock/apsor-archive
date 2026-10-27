"""Web search and web fetch orchestration with provider-versioned caching."""

import hashlib
import json
from typing import Literal

from app.module.web_research.domain.web_url_safety import WebUrlSafety
from app.module.web_research.exception.domain_error import (
    WebFetchNotConfiguredError,
    WebProviderError,
    WebSearchNotConfiguredError,
)
from app.module.web_research.protocol.web_cache_protocol import (
    JsonValue,
    WebCacheProtocol,
)
from app.module.web_research.protocol.web_client_protocol import (
    WebFetchClientProtocol,
    WebSearchClientProtocol,
)
from app.module.web_research.protocol.web_provider_config_protocol import (
    WebProviderConfigProtocol,
)
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchHit,
    WebSearchResponse,
)

# Content cap for a single search result: a provider may return a whole page of
# text, and only the excerpt needed for the agent to judge whether the result is
# worth a web_fetch is kept here, so neither the tool result nor the SSE payload
# grows too large.
_MAX_SEARCH_CONTENT_CHARS = 8_000
_MAX_SEARCH_RESULTS = 10
_MAX_DOMAINS = 10
_DEFAULT_FETCH_MAX_CHARS = 20_000

# web_fetch caches by "complete document": one URL is fetched from the provider
# only once, and later page numbers are sliced locally. The schema marker, wrap
# width, page budget, and full-text limit all go into the cache key, so any change
# in meaning naturally invalidates the old entries.
_FETCH_CACHE_SCHEMA = "v3"
_MAX_FETCH_CACHE_CHARS = 2_000_000

# The page size is decided by the server: 12,000 characters by default, actually
# min(_FETCH_PAGE_CHARS, fetch_max_chars). The model only sees page and never has
# to compute an offset.
_FETCH_PAGE_CHARS = 12_000

# The hard wrap width is deliberately smaller than the page budget (12,000 by
# default, 1,000 as the configured minimum): any single line always fits in one
# page, so the page number can always advance instead of getting stuck repeating
# the same page because one line exceeds the limit.
_MAX_FETCH_WRAP_CHARS = 800


class WebResearchService:
    """Coordinate one provider config, one client and the shared cache.

    The service never opens a database session. It is built per request from the
    runtime snapshot (``app.state.ai_runtime``), so provider writes are visible
    on the next call without holding a connection during an SSE stream.
    """

    def __init__(
        self,
        *,
        search_config: WebProviderConfigProtocol,
        fetch_config: WebProviderConfigProtocol,
        search_client: WebSearchClientProtocol,
        fetch_client: WebFetchClientProtocol,
        cache: WebCacheProtocol,
        search_ttl_seconds: int = 900,
        fetch_ttl_seconds: int = 3_600,
        fetch_max_chars: int = _DEFAULT_FETCH_MAX_CHARS,
    ) -> None:
        self._search_config = search_config
        self._fetch_config = fetch_config
        self._search_client = search_client
        self._fetch_client = fetch_client
        self._cache = cache
        self._search_ttl_seconds = search_ttl_seconds
        self._fetch_ttl_seconds = fetch_ttl_seconds
        # A page must always be able to hold one wrapped line. The default
        # setting is far above this floor; the clamp keeps pagination moving
        # even if an operator configures an unusually small value.
        self._fetch_max_chars = max(_MAX_FETCH_WRAP_CHARS + 1, fetch_max_chars)

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> WebSearchResponse:
        """Search the web, returning a cached response when one exists."""
        normalized_query = query.strip()
        if not normalized_query:
            raise WebProviderError("search query must not be empty.")
        bounded_results = max(1, min(max_results, _MAX_SEARCH_RESULTS))
        include = _normalize_domains(include_domains)
        exclude = _normalize_domains(exclude_domains)

        # Only the normalized arguments go into the hash input; cache_key() applies
        # SHA-256 on top, so the raw query never appears in plain text in a Valkey
        # key, a log line, or a metric.
        canonical_args = json.dumps(
            {
                "exclude_domains": exclude,
                "include_domains": include,
                "max_results": bounded_results,
                "query": normalized_query,
                "search_depth": search_depth,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        key = _cache_key(
            await self._cache.get_version("providers"),
            "web_search",
            canonical_args,
        )
        cached = _validate_cached(WebSearchResponse, await self._cache.get_json(key))
        if cached is not None:
            return cached.model_copy(update={"cached": True})

        # Only a cache miss checks the configuration: a cache hit means the
        # provider settings version has not changed, so the existing result should
        # be returned even if no key is configured at the moment.
        if not _is_ready(self._search_config, self._search_client):
            raise WebSearchNotConfiguredError()

        response = await self._search_client.search(
            normalized_query,
            max_results=bounded_results,
            search_depth=search_depth,
            include_domains=include,
            exclude_domains=exclude,
        )
        hits: list[WebSearchHit] = []
        truncated = response.truncated
        for hit in response.results:
            content = hit.content
            if len(content) > _MAX_SEARCH_CONTENT_CHARS:
                content = content[:_MAX_SEARCH_CONTENT_CHARS]
                truncated = True
            hits.append(hit.model_copy(update={"content": content}))
        response = response.model_copy(
            update={
                "provider": self._search_config.provider,
                "results": hits,
                "truncated": truncated,
                "cached": False,
            }
        )
        await self._cache.set_json(
            key,
            response.model_dump(mode="json"),
            self._search_ttl_seconds,
        )
        return response

    async def fetch(
        self,
        url: str,
        *,
        page: int | None = None,
        offset: int | None = None,
    ) -> WebFetchResponse:
        """Fetch one public URL and return one server-defined Markdown page.

        The full normalized document is cached once per URL; pages are computed
        locally from a fixed character budget. ``page`` is the supported
        surface. ``offset`` is accepted only for conversations frozen on the
        old line-offset tool schema: it selects the page that contains that
        1-based line. If a direct caller supplies both, ``page`` wins (the tool
        argument model already rejects that combination).
        """
        # WebUrlSafety returns a normalized URL (lowercase scheme/host, default port
        # removed, fragment removed); the normalized string is also the fetch cache
        # key input, so one resource has exactly one cache entry.
        normalized_url = WebUrlSafety.validate(url)
        # The page budget is part of the server-side semantics; putting it in the
        # cache key means any change to the configured page size or full-text limit
        # naturally produces a new cache entry.
        page_chars = min(_FETCH_PAGE_CHARS, self._fetch_max_chars)
        key = _cache_key(
            await self._cache.get_version("providers"),
            "web_fetch",
            normalized_url,
            _FETCH_CACHE_SCHEMA,
            str(_MAX_FETCH_WRAP_CHARS),
            str(page_chars),
            str(_MAX_FETCH_CACHE_CHARS),
        )
        cached = _validate_cached(WebFetchResponse, await self._cache.get_json(key))
        if cached is not None:
            # A cache hit means the provider settings version has not changed; the
            # existing full text should be returned even if no key is configured at
            # the moment, so configured is not checked again here.
            return _slice_fetch_page(
                cached,
                page=page,
                offset=offset,
                page_chars=page_chars,
                cached=True,
            )

        if not _is_ready(self._fetch_config, self._fetch_client):
            raise WebFetchNotConfiguredError()

        # Fetch the complete content from the provider only once; the client's
        # max_chars is a hint for the full-text limit, and the actual paging is done
        # by _slice_fetch_page against a fixed character budget.
        response = await self._fetch_client.fetch(
            normalized_url,
            max_chars=_MAX_FETCH_CACHE_CHARS,
        )
        content = _normalize_fetch_text(response.content)
        if not content.strip():
            raise WebProviderError("the page produced no extractable text")
        source_truncated = response.truncated
        if len(content) > _MAX_FETCH_CACHE_CHARS:
            content = content[:_MAX_FETCH_CACHE_CHARS]
            source_truncated = True
        full = _full_fetch_response(
            response,
            provider=self._fetch_config.provider,
            content=content,
            source_truncated=source_truncated,
            page_chars=page_chars,
        )
        await self._cache.set_json(
            key,
            full.model_dump(mode="json"),
            self._fetch_ttl_seconds,
        )
        return _slice_fetch_page(
            full,
            page=page,
            offset=offset,
            page_chars=page_chars,
            cached=False,
        )


def _slice_fetch_page(
    full: WebFetchResponse,
    *,
    page: int | None,
    offset: int | None,
    page_chars: int,
    cached: bool,
) -> WebFetchResponse:
    """Return one fresh page without mutating the cached full document.

    Pages are contiguous ``[start, end)`` line ranges. The requested page is
    either explicit (``page``), legacy-mapped from a 1-based line (``offset``),
    or page 1. An out-of-range request returns an empty page with the real
    totals instead of raising.
    """
    lines = full.content.split("\n")
    ranges = _page_ranges(lines, page_chars)
    total_pages = max(1, len(ranges))
    total_chars = len(full.content)
    source_truncated = full.source_truncated
    if page is not None:
        requested_page = page
    elif offset is not None:
        requested_page = _page_for_line(ranges, offset)
    else:
        requested_page = 1

    if requested_page < 1 or requested_page > total_pages:
        return WebFetchResponse(
            provider=full.provider,
            url=full.url,
            content="",
            elapsed_ms=full.elapsed_ms,
            truncated=source_truncated,
            cached=cached,
            retrieved_at=full.retrieved_at,
            page=requested_page,
            total_pages=total_pages,
            page_chars=0,
            total_chars=total_chars,
            has_more=False,
            next_page=None,
            source_truncated=source_truncated,
        )

    start, end = ranges[requested_page - 1]
    content = "\n".join(lines[start:end])
    has_more = requested_page < total_pages
    return WebFetchResponse(
        provider=full.provider,
        url=full.url,
        content=content,
        elapsed_ms=full.elapsed_ms,
        truncated=has_more or source_truncated,
        cached=cached,
        retrieved_at=full.retrieved_at,
        page=requested_page,
        total_pages=total_pages,
        page_chars=len(content),
        total_chars=total_chars,
        has_more=has_more,
        next_page=requested_page + 1 if has_more else None,
        source_truncated=source_truncated,
    )


def _page_ranges(lines: list[str], page_chars: int) -> list[tuple[int, int]]:
    """Pack whole lines into contiguous pages under a character budget.

    The budget counts the newline separators that ``"\n".join`` will insert, so
    a rendered page never exceeds ``page_chars`` as long as each individual line
    is shorter than the budget. ``_MAX_FETCH_WRAP_CHARS`` (800) guarantees that
    for the 12,000-character default. As a defensive fallback, a page always
    takes at least one line, so pagination can never stall on a misconfigured
    tiny budget.
    """
    if not lines:
        return [(0, 0)]
    budget = max(1, page_chars)
    ranges: list[tuple[int, int]] = []
    start = 0
    used = 0
    index = 0
    while index < len(lines):
        added = len(lines[index]) + (1 if index > start else 0)
        if index > start and used + added > budget:
            ranges.append((start, index))
            start = index
            used = 0
            continue
        used += added
        index += 1
    ranges.append((start, len(lines)))
    return ranges


def _page_for_line(ranges: list[tuple[int, int]], offset: int) -> int:
    """Map a legacy 1-based line number to the page that contains it.

    An offset past the last line returns one page past the end, which the caller
    turns into the empty out-of-range response.
    """
    line_index = offset - 1
    if line_index < 0:
        return 1
    for page_index, (start, end) in enumerate(ranges, start=1):
        if start <= line_index < end:
            return page_index
    return len(ranges) + 1


def _normalize_fetch_text(content: str) -> str:
    """Normalize line endings and hard-wrap very long lines.

    Wrapping is what makes page pagination always progress: every line becomes
    at most 800 characters, which is below the 12,000-character default page
    budget. Every original character is preserved; only newlines are inserted.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized:
        return ""
    lines: list[str] = []
    for line in normalized.split("\n"):
        if len(line) <= _MAX_FETCH_WRAP_CHARS:
            lines.append(line)
            continue
        lines.extend(
            line[start : start + _MAX_FETCH_WRAP_CHARS]
            for start in range(0, len(line), _MAX_FETCH_WRAP_CHARS)
        )
    return "\n".join(lines)


def _full_fetch_response(
    response: WebFetchResponse,
    *,
    provider: str,
    content: str,
    source_truncated: bool,
    page_chars: int,
) -> WebFetchResponse:
    """Build the full-document cache payload that every page starts from.

    The payload describes the whole document as page 1 with no continuation;
    ``_slice_fetch_page`` recomputes the real slice for every request.
    """
    lines = content.split("\n")
    total_pages = max(1, len(_page_ranges(lines, page_chars)))
    return response.model_copy(
        update={
            "provider": provider,
            "content": content,
            "truncated": source_truncated,
            "cached": False,
            "page": 1,
            "total_pages": total_pages,
            "page_chars": len(content),
            "total_chars": len(content),
            "has_more": False,
            "next_page": None,
            "source_truncated": source_truncated,
        }
    )


def _is_ready(
    config: WebProviderConfigProtocol,
    client: WebSearchClientProtocol | WebFetchClientProtocol,
) -> bool:
    """Return whether a provider can actually serve a request.

    Both ``enabled`` and ``provider != "none"`` must hold; the key is only ever
    tested as a boolean here and is never written into a message or the cache.
    ``client.configured`` is the second safety net, so a registry entry that looks
    enabled but whose client has no credentials does not send an empty-key
    request.
    """
    return (
        config.enabled
        and config.provider != "none"
        and bool(config.api_key)
        and client.configured
        and client.provider == config.provider
    )


def _normalize_domains(domains: list[str]) -> list[str]:
    """Lowercase, deduplicate and sort domain filters for a stable cache key."""
    cleaned = {domain.strip().lower() for domain in domains if domain.strip()}
    return sorted(cleaned)[:_MAX_DOMAINS]


def _validate_cached[T: (WebSearchResponse, WebFetchResponse)](
    model: type[T],
    payload: JsonValue | None,
) -> T | None:
    """Decode a cache payload, treating corrupt data as a miss rather than an error."""
    if payload is None:
        return None
    try:
        return model.model_validate(payload)
    except ValueError:
        # An old schema version or a corrupted payload must not fail the user's
        # request; it is simply treated as a cache miss.
        return None


def _cache_key(version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key whose parts are hashed, never stored raw.

    The format matches the knowledge slice's ``cache_key``
    (``apsor:<version>:<namespace>:<digest>``). The web slice must not import
    another slice's service module, so this pure function is kept locally. The
    digest keeps the raw query / URL out of the cache key in plain text.
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{namespace}:{digest}"
