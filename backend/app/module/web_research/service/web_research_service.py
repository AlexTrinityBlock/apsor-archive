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

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        """Fetch one public URL as Markdown, clipped at the service boundary."""
        # WebUrlSafety 回傳正規化 URL（小寫 scheme/host、去預設 port、去 fragment），
        # 正規化後的字串同時是 fetch cache key 的輸入，確保同一資源只有一份 cache。
        normalized_url = WebUrlSafety.validate(url)
        bounded_chars = max(1, min(max_chars, self._fetch_max_chars))
        key = _cache_key(
            await self._cache.get_version("providers"),
            "web_fetch",
            normalized_url,
            str(bounded_chars),
        )
        cached = _validate_cached(WebFetchResponse, await self._cache.get_json(key))
        if cached is not None:
            return cached.model_copy(update={"cached": True})

        if not _is_ready(self._fetch_config, self._fetch_client):
            raise WebFetchNotConfiguredError()

        response = await self._fetch_client.fetch(normalized_url, max_chars=bounded_chars)
        content = response.content
        truncated = response.truncated
        # 裁切統一在 service 邊界做：cache 內存的就是實際回傳給呼叫端的內容，
        # cache key 也綁定 max_chars，不會出現「同一 key 卻長度不同」的情況。
        if len(content) > bounded_chars:
            content = content[:bounded_chars]
            truncated = True
        response = response.model_copy(
            update={
                "provider": self._fetch_config.provider,
                "content": content,
                "truncated": truncated,
                "cached": False,
            }
        )
        await self._cache.set_json(
            key,
            response.model_dump(mode="json"),
            self._fetch_ttl_seconds,
        )
        return response


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

    格式與 knowledge 片的 ``cache_key`` 相同（``dendro:<version>:<namespace>:<digest>``）。
    web slice 不得 import 另一片的 service 模組，因此在本地保留這份純函式。
    digest 讓原始 query / URL 不會以明文出現在 cache key 中。
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"dendro:{version}:{namespace}:{digest}"
