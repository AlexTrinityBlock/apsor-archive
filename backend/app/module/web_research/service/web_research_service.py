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
_MAX_FETCH_LINES_PER_CALL = 2_000

# web_fetch 以「完整文件」為快取單位：同一個 URL 只向 provider 抓一次，後續
# 頁碼只做本機切片。schema marker 與全文上限都放進 cache key，任何語意變更
# 都會讓舊資料自然失效。
_FETCH_CACHE_SCHEMA = "v2"
_MAX_FETCH_CACHE_CHARS = 2_000_000

# 硬折行寬度刻意小於 max_chars 的最小值（1,000）：任何一行都一定塞得進單次
# 回應，行式分頁因此永遠能前進，不會卡在「一行超過上限」而重複同一頁。
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
        self._fetch_max_chars = max(1, fetch_max_chars)

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
        max_chars: int,
        offset: int = 1,
        limit: int = 200,
        page: int | None = None,
    ) -> WebFetchResponse:
        """Fetch one public URL and return one line-bounded Markdown slice.

        The full normalized document is cached once per URL. ``offset`` is a
        1-based line number and ``page`` is a 1-based window of ``limit``
        lines; both the argument model and the tool layer reject supplying
        both explicitly, so if a direct caller does, ``page`` wins.
        """
        # WebUrlSafety 回傳正規化 URL（小寫 scheme/host、去預設 port、去 fragment），
        # 正規化後的字串同時是 fetch cache key 的輸入，確保同一資源只有一份 cache。
        normalized_url = WebUrlSafety.validate(url)
        key = _cache_key(
            await self._cache.get_version("providers"),
            "web_fetch",
            normalized_url,
            _FETCH_CACHE_SCHEMA,
            str(_MAX_FETCH_WRAP_CHARS),
            str(_MAX_FETCH_CACHE_CHARS),
        )
        cached = _validate_cached(WebFetchResponse, await self._cache.get_json(key))
        if cached is not None:
            # cache 命中代表 provider 設定版本未變；即使目前暫時沒有金鑰也應該
            # 回傳既有全文，因此這裡不重新檢查 configured。
            return self._slice_fetch(
                cached,
                max_chars=max_chars,
                offset=offset,
                limit=limit,
                page=page,
                cached=True,
            )

        if not _is_ready(self._fetch_config, self._fetch_client):
            raise WebFetchNotConfiguredError()

        # 只向 provider 抓一次完整內容；client 的 max_chars 是全文上限提示，
        # 真正的切片由 _slice_fetch 依行號完成。
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
        )
        await self._cache.set_json(
            key,
            full.model_dump(mode="json"),
            self._fetch_ttl_seconds,
        )
        return self._slice_fetch(
            full,
            max_chars=max_chars,
            offset=offset,
            limit=limit,
            page=page,
            cached=False,
        )

    def _slice_fetch(
        self,
        full: WebFetchResponse,
        *,
        max_chars: int,
        offset: int,
        limit: int,
        page: int | None,
        cached: bool,
    ) -> WebFetchResponse:
        """Return one fresh response slice without mutating the cached document."""
        bounded_chars = max(1, min(max_chars, self._fetch_max_chars))
        bounded_limit = max(1, min(limit, _MAX_FETCH_LINES_PER_CALL))
        lines = full.content.split("\n")
        total_lines = len(lines)
        total_pages = max(1, (total_lines + bounded_limit - 1) // bounded_limit)
        source_truncated = full.truncated
        # page 模式與 offset 模式都只影響起點；offset/page 衝突已在 args 層
        # 擋下，因此服務層直接讓 page 優先。
        start_index = (page - 1) * bounded_limit if page is not None else offset - 1

        if start_index >= total_lines:
            return WebFetchResponse(
                provider=full.provider,
                url=full.url,
                content="",
                elapsed_ms=full.elapsed_ms,
                truncated=source_truncated,
                cached=cached,
                retrieved_at=full.retrieved_at,
                offset=start_index + 1,
                limit=bounded_limit,
                page=start_index // bounded_limit + 1,
                total_pages=total_pages,
                total_lines=total_lines,
                total_chars=len(full.content),
                returned_lines=0,
                has_more=False,
                next_offset=None,
                next_page=None,
                source_truncated=source_truncated,
            )

        selected: list[str] = []
        used_chars = 0
        for line in lines[start_index : start_index + bounded_limit]:
            added_chars = len(line) + (1 if selected else 0)
            # 至少先放進一行：折行寬度 800 < max_chars 最小值 1,000，第一行
            # 一定放得下，後續才能靠 next_offset 穩定前進。
            if selected and used_chars + added_chars > bounded_chars:
                break
            selected.append(line)
            used_chars += added_chars

        returned_lines = len(selected)
        end_index = start_index + returned_lines
        has_more = end_index < total_lines
        next_offset = end_index + 1 if has_more else None
        current_page = start_index // bounded_limit + 1
        # next_page 只在切片剛好停在頁邊界時有效；max_chars 可能讓一頁提早
        # 結束，此時只有 next_offset 能保證不跳行。
        next_page = (
            current_page + 1
            if has_more and next_offset == current_page * bounded_limit + 1
            else None
        )
        return WebFetchResponse(
            provider=full.provider,
            url=full.url,
            content="\n".join(selected),
            elapsed_ms=full.elapsed_ms,
            truncated=has_more or source_truncated,
            cached=cached,
            retrieved_at=full.retrieved_at,
            offset=start_index + 1,
            limit=bounded_limit,
            page=current_page,
            total_pages=total_pages,
            total_lines=total_lines,
            total_chars=len(full.content),
            returned_lines=returned_lines,
            has_more=has_more,
            next_offset=next_offset,
            next_page=next_page,
            source_truncated=source_truncated,
        )


def _normalize_fetch_text(content: str) -> str:
    """Normalize line endings and hard-wrap very long lines.

    Wrapping is what makes line pagination always progress: every line becomes
    at most 800 characters, which is below the 1,000-character minimum
    ``max_chars``. Every original character is preserved; only newlines are
    inserted.
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
) -> WebFetchResponse:
    """Build the full-document cache payload that every slice starts from."""
    total_lines = content.count("\n") + 1
    total_pages = max(
        1,
        (total_lines + _MAX_FETCH_LINES_PER_CALL - 1) // _MAX_FETCH_LINES_PER_CALL,
    )
    return response.model_copy(
        update={
            "provider": provider,
            "content": content,
            "truncated": source_truncated,
            "cached": False,
            "offset": 1,
            "limit": _MAX_FETCH_LINES_PER_CALL,
            "page": 1,
            "total_pages": total_pages,
            "total_lines": total_lines,
            "total_chars": len(content),
            "returned_lines": total_lines,
            "has_more": False,
            "next_offset": None,
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
