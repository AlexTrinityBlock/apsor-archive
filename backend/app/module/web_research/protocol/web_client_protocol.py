"""Consumer-owned contracts for web search and web fetch clients."""

from typing import Literal, Protocol

from app.module.web_research.protocol.web_provider_config_protocol import (
    WebProviderConfigProtocol,
)
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchResponse,
)


class WebSearchClientProtocol(Protocol):
    """One provider's search implementation.

    ``provider`` is the registry kind (for example ``tavily``) and ``configured``
    reports whether the client holds a usable credential.
    """

    provider: str
    configured: bool

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> WebSearchResponse: ...


class WebFetchClientProtocol(Protocol):
    """One provider's URL-to-Markdown implementation."""

    provider: str
    configured: bool

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse: ...


class WebClientFactoryProtocol(Protocol):
    """Build clients from a resolved configuration snapshot."""

    def build_search(self, config: WebProviderConfigProtocol) -> WebSearchClientProtocol: ...

    def build_fetch(self, config: WebProviderConfigProtocol) -> WebFetchClientProtocol: ...
