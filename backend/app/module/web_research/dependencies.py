"""Composition root for the web research slice.

The production service is built per request from ``app.state.ai_runtime``.
The runtime snapshot already holds the active ``web_search`` / ``web_fetch``
configurations and is reloaded on every provider write, so a search or fetch
never needs a database session — important while an agent SSE stream is open.

Tests replace the whole slice by setting ``app.state.web_research_service`` to a
fake exposing the same ``search`` / ``fetch`` methods; no provider is then
called.
"""

from dataclasses import dataclass
from typing import Literal, cast

from fastapi import Request

from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import Database
from app.infrastructure.web.deepseek_web_client import DEFAULT_BASE_URL as DEEPSEEK_DEFAULT_BASE_URL
from app.infrastructure.web.deepseek_web_client import DeepSeekWebClient
from app.infrastructure.web.exa_client import DEFAULT_BASE_URL as EXA_DEFAULT_BASE_URL
from app.infrastructure.web.exa_client import ExaWebClient
from app.infrastructure.web.tavily_client import DEFAULT_BASE_URL as TAVILY_DEFAULT_BASE_URL
from app.infrastructure.web.tavily_client import TavilyWebClient
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.web_research.exception.domain_error import WebProviderError
from app.module.web_research.protocol.web_cache_protocol import WebCacheProtocol
from app.module.web_research.protocol.web_client_protocol import (
    WebClientFactoryProtocol,
    WebFetchClientProtocol,
    WebSearchClientProtocol,
)
from app.module.web_research.protocol.web_provider_config_protocol import (
    WebProviderConfigProtocol,
)
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchResponse,
)
from app.module.web_research.service.web_research_service import WebResearchService


@dataclass(frozen=True)
class _UnconfiguredWebConfig:
    """Stands in for a capability that has no runtime snapshot yet."""

    capability: str
    provider: str = "none"
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool = False
    source: str = "default"


class DisabledWebClient:
    """A provider-less client whose readiness check always fails closed."""

    provider = "none"
    configured = False

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
        del query, max_results, search_depth, include_domains, exclude_domains, objective
        raise WebProviderError("No web search provider is configured.")

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        del url, max_chars
        raise WebProviderError("No web fetch provider is configured.")


class WebClientFactory:
    """Build the selected web clients from runtime configuration only.

    No database access and no logging: the factory receives the plaintext key
    from the in-memory snapshot and hands it straight to the HTTP client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _base_url(self, config: WebProviderConfigProtocol) -> str:
        # The user can override base_url in the registry. A stale default from
        # another provider is ignored so switching the dropdown cannot send one
        # provider's traffic to another provider's origin.
        if config.provider == "exa":
            base = (config.base_url or "").rstrip("/")
            if not base or base in {TAVILY_DEFAULT_BASE_URL, DEEPSEEK_DEFAULT_BASE_URL}:
                base = str(
                    getattr(self._settings, "exa_base_url", EXA_DEFAULT_BASE_URL)
                    or EXA_DEFAULT_BASE_URL
                )
            return base
        if config.provider == "deepseek":
            base = (config.base_url or "").rstrip("/")
            if not base or base in {TAVILY_DEFAULT_BASE_URL, EXA_DEFAULT_BASE_URL}:
                base = str(
                    getattr(self._settings, "deepseek_base_url", DEEPSEEK_DEFAULT_BASE_URL)
                    or DEEPSEEK_DEFAULT_BASE_URL
                )
            return base
        base = (config.base_url or "").rstrip("/")
        if not base or base in {EXA_DEFAULT_BASE_URL, DEEPSEEK_DEFAULT_BASE_URL}:
            base = str(
                getattr(self._settings, "tavily_base_url", TAVILY_DEFAULT_BASE_URL)
                or TAVILY_DEFAULT_BASE_URL
            )
        return base

    def build_search(self, config: WebProviderConfigProtocol) -> WebSearchClientProtocol:
        timeout_seconds = float(getattr(self._settings, "web_search_timeout_seconds", 25.0))
        if config.provider == "exa":
            return ExaWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
            )
        if config.provider == "deepseek":
            return DeepSeekWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
            )
        if config.provider == "tavily":
            return TavilyWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
                extract_depth=getattr(self._settings, "tavily_extract_depth", "advanced"),
            )
        return DisabledWebClient()

    def build_fetch(self, config: WebProviderConfigProtocol) -> WebFetchClientProtocol:
        timeout_seconds = float(getattr(self._settings, "web_fetch_timeout_seconds", 45.0))
        if config.provider == "exa":
            return ExaWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
            )
        if config.provider == "deepseek":
            return DeepSeekWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
            )
        if config.provider == "tavily":
            return TavilyWebClient(
                api_key=config.api_key,
                base_url=self._base_url(config),
                timeout_seconds=timeout_seconds,
                extract_depth=getattr(self._settings, "tavily_extract_depth", "advanced"),
            )
        return DisabledWebClient()


def get_web_research_service(
    request: Request,
    *,
    user_id: int | None = None,
) -> WebResearchService:
    """Resolve the web research service, honouring a test/runtime override.

    ``user_id`` is supplied by the agent tool scope so the service can enforce
    and record the captured account's web allowance. Callers without an account
    (and the test override) get no quota policy.
    """
    override = getattr(request.app.state, "web_research_service", None)
    if override is not None:
        return cast(WebResearchService, override)
    return _build_web_research_service(request, user_id=user_id)


def _build_web_research_service(
    request: Request,
    *,
    user_id: int | None = None,
) -> WebResearchService:
    settings = cast(Settings, request.app.state.settings)
    runtime = request.app.state.ai_runtime
    # Provider settings are only read from the runtime snapshot: no DB session is
    # opened during SSE, and a provider write triggers runtime.reload() so the next
    # tool call already sees the new settings.
    search_config = _runtime_config(runtime, "web_search_config", "web_search")
    fetch_config = _runtime_config(runtime, "web_fetch_config", "web_fetch")
    factory: WebClientFactoryProtocol = WebClientFactory(settings)
    quota = (
        AccountQuotaService(cast(Database, request.app.state.db), user_id)
        if user_id is not None
        else None
    )
    return WebResearchService(
        search_config=search_config,
        fetch_config=fetch_config,
        search_client=factory.build_search(search_config),
        fetch_client=factory.build_fetch(fetch_config),
        cache=cast(WebCacheProtocol, request.app.state.cache),
        search_ttl_seconds=int(getattr(settings, "web_search_cache_ttl_seconds", 900)),
        fetch_ttl_seconds=int(getattr(settings, "web_fetch_cache_ttl_seconds", 3_600)),
        fetch_max_chars=int(getattr(settings, "web_fetch_max_chars", 20_000)),
        quota=quota,
    )


def _runtime_config(
    runtime: object,
    attribute: str,
    capability: str,
) -> WebProviderConfigProtocol:
    config = getattr(runtime, attribute, None)
    if config is None:
        return _UnconfiguredWebConfig(capability=capability)
    return cast(WebProviderConfigProtocol, config)


__all__ = ["WebClientFactory", "get_web_research_service"]
