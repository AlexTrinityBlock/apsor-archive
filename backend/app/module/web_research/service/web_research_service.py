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

# 單一搜尋結果的內容上限：provider 可能回傳整頁內文，這裡只留足以讓 agent
# 判斷是否值得 web_fetch 的摘要，避免 tool result 與 SSE payload 過大。
_MAX_SEARCH_CONTENT_CHARS = 8_000
_MAX_SEARCH_RESULTS = 10
_MAX_DOMAINS = 10
_DEFAULT_FETCH_MAX_CHARS = 20_000

# web_fetch 以「完整文件」為快取單位：同一個 URL 只向 provider 抓一次，後續
# 頁碼只做本機切片。schema marker、折行寬度、頁面預算與全文上限都放進 cache
# key，任何語意變更都會讓舊資料自然失效。
_FETCH_CACHE_SCHEMA = "v3"
_MAX_FETCH_CACHE_CHARS = 2_000_000

# 頁面大小由 server 決定：預設 12,000 字元，實際值是
# min(_FETCH_PAGE_CHARS, fetch_max_chars)。模型只看 page，不必計算 offset。
_FETCH_PAGE_CHARS = 12_000

# 硬折行寬度刻意小於頁面預算（預設 12,000；設定下限 1,000）：任何一行都一定
# 塞得進一頁，頁碼因此永遠能前進，不會卡在「一行超過上限」而重複同一頁。
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

        # 只把「正規化後的參數」放進雜湊輸入；cache_key() 會再做 SHA-256，
        # 因此原始 query 不會以明文出現在 Valkey key、log 或 metrics 中。
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

        # Cache miss 才檢查設定：cache 命中代表 provider 設定版本未變，
        # 即使目前暫時沒有金鑰也應該回傳既有結果。
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
        # WebUrlSafety 回傳正規化 URL（小寫 scheme/host、去預設 port、去 fragment），
        # 正規化後的字串同時是 fetch cache key 的輸入，確保同一資源只有一份 cache。
        normalized_url = WebUrlSafety.validate(url)
        # 頁面預算是 server 端語意的一部分，放進 cache key 後，任何站台設定的
        # 頁面大小或全文上限變更都會自然產生新的 cache entry。
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
            # cache 命中代表 provider 設定版本未變；即使目前暫時沒有金鑰也應該
            # 回傳既有全文，因此這裡不重新檢查 configured。
            return _slice_fetch_page(
                cached,
                page=page,
                offset=offset,
                page_chars=page_chars,
                cached=True,
            )

        if not _is_ready(self._fetch_config, self._fetch_client):
            raise WebFetchNotConfiguredError()

        # 只向 provider 抓一次完整內容；client 的 max_chars 是全文上限提示，
        # 真正的切頁由 _slice_fetch_page 依固定字元預算完成。
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

    ``enabled`` 與 ``provider != "none"`` 都必須成立；金鑰只在此處做布林判斷，
    不會被寫入訊息或 cache。``client.configured`` 是第二道保險，避免 registry
    顯示已啟用但實際 client 沒有憑證時仍送出空金鑰請求。
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
        # 舊版 schema 或損壞的 payload 不應讓使用者請求失敗；直接當作 cache miss。
        return None


def _cache_key(version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key whose parts are hashed, never stored raw.

    格式與 knowledge 片的 ``cache_key`` 相同（``apsor:<version>:<namespace>:<digest>``）。
    web slice 不得 import 另一片的 service 模組，因此在本地保留這份純函式。
    digest 讓原始 query / URL 不會以明文出現在 cache key 中。
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{namespace}:{digest}"
