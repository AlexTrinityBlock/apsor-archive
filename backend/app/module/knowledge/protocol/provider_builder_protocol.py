"""Pure contract for turning provider configuration into clients."""

from typing import Any, Literal, Protocol

from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol


class WebClientProtocol(Protocol):
    """Minimal structural contract for a web search/fetch client.

    The concrete Tavily client lives in ``app/infrastructure/web`` and is owned
    by the web-research slice.  Knowledge deliberately does not import that
    module: it only needs the two safe status attributes here, plus the two
    request methods used by the connection tester.  ``Any`` is used for the
    response types because the concrete response models belong to the web
    slice; knowledge never reads their fields.
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
    ) -> Any: ...

    async def fetch(self, url: str, *, max_chars: int) -> Any: ...


class ProviderBuilderProtocol(Protocol):
    """Build infrastructure clients from resolved configuration."""

    def build_text_generator(self, config: ProviderConfig) -> TextGeneratorProtocol: ...

    def build_embedder(self, config: ProviderConfig) -> EmbedderProtocol: ...

    def build_web_client(self, config: ProviderConfig) -> WebClientProtocol: ...


__all__ = ["ProviderBuilderProtocol", "WebClientProtocol"]
