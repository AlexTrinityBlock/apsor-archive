"""Composition root for the web research slice.

The production service is built per request from ``app.state.ai_runtime``.
The runtime snapshot already holds the active ``web_search`` / ``web_fetch``
configurations and is reloaded on every provider write, so a search or fetch
never needs a database session — important while an agent SSE stream is open.

Tests replace the whole slice by setting ``app.state.web_research_service`` to a
fake exposing the same ``search`` / ``fetch`` methods; Tavily is then never
called.
"""

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.infrastructure.config.settings import Settings
from app.infrastructure.web.tavily_client import DEFAULT_BASE_URL, TavilyWebClient
from app.module.web_research.protocol.web_cache_protocol import WebCacheProtocol
from app.module.web_research.protocol.web_client_protocol import (
    WebClientFactoryProtocol,
    WebFetchClientProtocol,
    WebSearchClientProtocol,
)
from app.module.web_research.protocol.web_provider_config_protocol import (
    WebProviderConfigProtocol,
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


class TavilyWebClientFactory:
    """Build Tavily clients from runtime configuration only.

    No database access and no logging: the factory receives the plaintext key
    from the in-memory snapshot and hands it straight to the HTTP client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _base_url(self, config: WebProviderConfigProtocol) -> str:
        # The user can override base_url in the registry; otherwise the deployment's
        # Tavily base URL is used.
        return config.base_url or str(
            getattr(self._settings, "tavily_base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
        )

    def build_search(self, config: WebProviderConfigProtocol) -> WebSearchClientProtocol:
        return TavilyWebClient(
            api_key=config.api_key,
            base_url=self._base_url(config),
            timeout_seconds=float(getattr(self._settings, "web_search_timeout_seconds", 25.0)),
        )

    def build_fetch(self, config: WebProviderConfigProtocol) -> WebFetchClientProtocol:
        return TavilyWebClient(
            api_key=config.api_key,
            base_url=self._base_url(config),
            timeout_seconds=float(getattr(self._settings, "web_fetch_timeout_seconds", 30.0)),
        )


def get_web_research_service(request: Request) -> WebResearchService:
    """Resolve the web research service, honouring a test/runtime override."""
    override = getattr(request.app.state, "web_research_service", None)
    if override is not None:
        return cast(WebResearchService, override)
    return _build_web_research_service(request)


def _build_web_research_service(request: Request) -> WebResearchService:
    settings = cast(Settings, request.app.state.settings)
    runtime = request.app.state.ai_runtime
    # Provider settings are only read from the runtime snapshot: no DB session is
    # opened during SSE, and a provider write triggers runtime.reload() so the next
    # tool call already sees the new settings.
    search_config = _runtime_config(runtime, "web_search_config", "web_search")
    fetch_config = _runtime_config(runtime, "web_fetch_config", "web_fetch")
    factory: WebClientFactoryProtocol = TavilyWebClientFactory(settings)
    return WebResearchService(
        search_config=search_config,
        fetch_config=fetch_config,
        search_client=factory.build_search(search_config),
        fetch_client=factory.build_fetch(fetch_config),
        cache=cast(WebCacheProtocol, request.app.state.cache),
        search_ttl_seconds=int(getattr(settings, "web_search_cache_ttl_seconds", 900)),
        fetch_ttl_seconds=int(getattr(settings, "web_fetch_cache_ttl_seconds", 3_600)),
        fetch_max_chars=int(getattr(settings, "web_fetch_max_chars", 20_000)),
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


__all__ = ["TavilyWebClientFactory", "get_web_research_service"]
