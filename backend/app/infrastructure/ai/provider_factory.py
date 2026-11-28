"""Build clients from resolved provider configuration."""

import logging
from typing import cast

from app.infrastructure.ai.anthropic_client import AnthropicClient
from app.infrastructure.ai.deepseek_client import DeepSeekClient, NullTextGenerator
from app.infrastructure.config.settings import Settings
from app.infrastructure.embedding.hashing_embedder import HashingEmbedder
from app.infrastructure.embedding.http_embedder import (
    DisabledEmbedder,
    OpenAICompatibleEmbedder,
)
from app.module.knowledge.domain.provider_config_domain import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CAPABILITY_WEB_FETCH,
    CAPABILITY_WEB_SEARCH,
    CHAT_TABLE_SPEC,
    EMBEDDING_TABLE_SPEC,
    ProviderCapability,
)
from app.module.knowledge.domain.provider_runtime_domain import (
    ProviderConfig,
    ProviderDefaults,
)
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_builder_protocol import WebClientProtocol
from app.module.knowledge.protocol.provider_tester_protocol import (
    ProviderTesterProtocol,
    ProviderTestOutcome,
)
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol

logger = logging.getLogger(__name__)


class NullWebClient:
    """A disabled web client used when no web provider is configured."""

    provider = "none"
    configured = False

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: str,
        include_domains: list[str],
        exclude_domains: list[str],
        objective: str = "",
    ) -> object:
        del query, max_results, search_depth, include_domains, exclude_domains, objective
        raise RuntimeError("No web search provider is configured.")

    async def fetch(self, url: str, *, max_chars: int) -> object:
        raise RuntimeError("No web fetch provider is configured.")


def provider_defaults_from_settings(settings: Settings) -> ProviderDefaults:
    """Project environment settings into the provider runtime defaults."""
    tavily_key = (
        settings.tavily_api_key.get_secret_value() if settings.tavily_api_key is not None else None
    )
    exa_key = settings.exa_api_key.get_secret_value() if settings.exa_api_key is not None else None
    deepseek_key = (
        settings.deepseek_api_key.get_secret_value()
        if settings.deepseek_api_key is not None
        else None
    )
    anthropic_key = (
        settings.anthropic_api_key.get_secret_value()
        if settings.anthropic_api_key is not None
        else None
    )
    # Both web capabilities prefer DeepSeek when its key exists, then Tavily,
    # then Exa. The two capabilities remain independently selectable in
    # Settings, and a saved database row always takes precedence.
    search_provider, search_base_url, search_api_key = _first_web_provider(
        (
            ("deepseek", deepseek_key, settings.deepseek_base_url),
            ("tavily", tavily_key, settings.tavily_base_url),
            ("exa", exa_key, settings.exa_base_url),
        ),
        settings.tavily_base_url,
    )
    fetch_provider, fetch_base_url, fetch_api_key = _first_web_provider(
        (
            ("deepseek", deepseek_key, settings.deepseek_base_url),
            ("tavily", tavily_key, settings.tavily_base_url),
            ("exa", exa_key, settings.exa_base_url),
        ),
        settings.tavily_base_url,
    )
    return ProviderDefaults(
        chat_provider="deepseek",
        chat_model=settings.deepseek_model,
        chat_base_url=settings.deepseek_base_url,
        chat_api_key=(
            settings.deepseek_api_key.get_secret_value()
            if settings.deepseek_api_key is not None
            else None
        ),
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_base_url=settings.embedding_base_url,
        embedding_api_key=(
            settings.embedding_api_key.get_secret_value()
            if settings.embedding_api_key is not None
            else None
        ),
        embedding_dimension=settings.embedding_dimension,
        # Environment fallbacks for the two independent web capabilities; an
        # active database row always takes precedence.
        web_search_provider=search_provider,
        web_search_base_url=search_base_url,
        web_search_api_key=search_api_key,
        web_fetch_provider=fetch_provider,
        web_fetch_base_url=fetch_base_url,
        web_fetch_api_key=fetch_api_key,
        tavily_api_key=tavily_key,
        exa_api_key=exa_key,
        deepseek_api_key=deepseek_key,
        anthropic_api_key=anthropic_key,
    )


def _first_web_provider(
    candidates: tuple[tuple[str, str | None, str], ...],
    fallback_base_url: str,
) -> tuple[str, str, str | None]:
    """Return the first web provider with a usable environment key."""
    for provider, api_key, base_url in candidates:
        if api_key:
            return provider, base_url, api_key
    return "none", fallback_base_url, None


class ProviderFactory:
    """The only place that turns configuration into concrete clients."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_text_generator(self, config: ProviderConfig) -> TextGeneratorProtocol:
        if (
            not config.enabled
            or config.provider not in CHAT_TABLE_SPEC.allowed_providers
            or config.provider == "none"
            or not config.api_key
        ):
            return NullTextGenerator()
        if config.provider == "anthropic":
            # ``max_tokens`` is required by the Messages API, so the row cap (or
            # the deployment chat cap) is always passed. Base URL, model, key,
            # version, and effort all come from the resolved configuration.
            return AnthropicClient(
                api_key=config.api_key,
                base_url=config.base_url or self.settings.anthropic_base_url,
                model=config.model or self.settings.anthropic_model,
                timeout_seconds=self.settings.anthropic_timeout_seconds,
                max_tokens=self.settings.anthropic_max_tokens,
                chat_max_tokens=(
                    config.max_output_tokens or self.settings.chat_agent_max_output_tokens
                ),
                reasoning_effort=config.reasoning_effort,
                anthropic_version=self.settings.anthropic_version,
            )
        return DeepSeekClient(
            api_key=config.api_key,
            base_url=config.base_url or self.settings.deepseek_base_url,
            model=config.model or self.settings.deepseek_model,
            timeout_seconds=self.settings.deepseek_timeout_seconds,
            max_tokens=self.settings.deepseek_max_tokens,
            chat_max_tokens=self.settings.deepseek_chat_max_tokens,
            temperature=self.settings.deepseek_temperature,
            supports_thinking=config.provider == "deepseek",
            reasoning_effort=config.reasoning_effort,
        )

    def build_embedder(self, config: ProviderConfig) -> EmbedderProtocol:
        if not config.enabled or config.provider not in EMBEDDING_TABLE_SPEC.allowed_providers:
            return DisabledEmbedder()
        if config.provider == "none":
            return DisabledEmbedder()
        if config.provider == "hashing":
            return HashingEmbedder(
                dimension=config.dimension or self.settings.embedding_dimension,
                model_name=config.model or self.settings.embedding_model,
            )
        if not config.base_url:
            return DisabledEmbedder()
        return OpenAICompatibleEmbedder(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model or self.settings.embedding_model,
            dimension=config.dimension or self.settings.embedding_dimension,
            timeout_seconds=self.settings.embedding_timeout_seconds,
        )

    def build_web_client(self, config: ProviderConfig) -> WebClientProtocol:
        """Build a web client lazily so knowledge never imports web code at boot.

        The web-research slice owns ``app/infrastructure/web``. The imports are
        deferred here so knowledge can still boot while that slice does not
        exist; tests swap the real client out through the provider-tester seam,
        so no external request is made.
        """
        if not config.enabled or config.provider == "none" or not config.api_key:
            return NullWebClient()
        timeout_seconds = (
            self.settings.web_search_timeout_seconds
            if config.capability == CAPABILITY_WEB_SEARCH
            else self.settings.web_fetch_timeout_seconds
        )
        if config.provider == "exa":
            try:
                from app.infrastructure.web.exa_client import ExaWebClient
            except ImportError:  # The web slice is optional at boot time.
                logger.warning("Exa client is unavailable; web capabilities stay disabled.")
                return NullWebClient()
            return cast(
                WebClientProtocol,
                ExaWebClient(
                    api_key=config.api_key,
                    base_url=_web_base_url(
                        config,
                        default=self.settings.exa_base_url,
                        wrong_provider_defaults=(
                            "https://api.tavily.com",
                            "https://api.deepseek.com",
                        ),
                    ),
                    timeout_seconds=timeout_seconds,
                ),
            )
        if config.provider == "deepseek":
            try:
                from app.infrastructure.web.deepseek_web_client import DeepSeekWebClient
            except ImportError:  # The web slice is optional at boot time.
                logger.warning("DeepSeek client is unavailable; web capabilities stay disabled.")
                return NullWebClient()
            return cast(
                WebClientProtocol,
                DeepSeekWebClient(
                    api_key=config.api_key,
                    base_url=_web_base_url(
                        config,
                        default=self.settings.deepseek_base_url,
                        wrong_provider_defaults=(
                            "https://api.tavily.com",
                            "https://api.exa.ai",
                        ),
                    ),
                    timeout_seconds=timeout_seconds,
                ),
            )
        if config.provider != "tavily":
            return NullWebClient()
        try:
            from app.infrastructure.web.tavily_client import TavilyWebClient
        except ImportError:  # The web slice is optional at boot time.
            logger.warning("Tavily client is unavailable; web capabilities stay disabled.")
            return NullWebClient()
        return cast(
            WebClientProtocol,
            TavilyWebClient(
                api_key=config.api_key,
                base_url=_web_base_url(
                    config,
                    default=self.settings.tavily_base_url,
                    wrong_provider_defaults=(
                        "https://api.exa.ai",
                        "https://api.deepseek.com",
                    ),
                ),
                timeout_seconds=timeout_seconds,
                extract_depth=self.settings.tavily_extract_depth,
            ),
        )


def _web_base_url(
    config: ProviderConfig,
    *,
    default: str,
    wrong_provider_defaults: tuple[str, ...] = (),
) -> str:
    """Resolve a web provider origin, ignoring stale other-provider defaults."""
    base = (config.base_url or "").rstrip("/")
    stale = {value.rstrip("/") for value in wrong_provider_defaults}
    if not base or base in stale:
        return default
    return base


class ProviderClientTester(ProviderTesterProtocol):
    """Production connection tester built from the same factory as the runtime."""

    def __init__(self, factory: ProviderFactory, settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    async def test(
        self,
        capability: ProviderCapability,
        config: ProviderConfig,
    ) -> ProviderTestOutcome:
        if config.provider == "none":
            return ProviderTestOutcome(ok=False, detail="No provider is selected.")
        # A saved row may be inactive; the test must still exercise its settings.
        enabled_config = config.model_copy(update={"enabled": True})
        try:
            if capability == CAPABILITY_CHAT:
                generator = self.factory.build_text_generator(enabled_config)
                if not generator.configured:
                    return ProviderTestOutcome(ok=False, detail="No chat API key is configured.")
                await generator.complete_text(
                    "You are a connection test. Reply with OK.",
                    "OK",
                )
            elif capability == CAPABILITY_EMBEDDING:
                embedder = self.factory.build_embedder(enabled_config)
                if embedder.dimension <= 0:
                    return ProviderTestOutcome(ok=False, detail="Embeddings are disabled.")
                await embedder.embed(["Apsor Archive connection test"])
            elif capability == CAPABILITY_WEB_SEARCH:
                client = self.factory.build_web_client(enabled_config)
                if not client.configured:
                    return ProviderTestOutcome(
                        ok=False,
                        detail="No web search API key is configured.",
                    )
                await client.search(
                    "Apsor Archive connection test",
                    max_results=1,
                    search_depth="basic",
                    include_domains=[],
                    exclude_domains=[],
                    objective="Verify the configured web search provider connection.",
                )
            elif capability == CAPABILITY_WEB_FETCH:
                client = self.factory.build_web_client(enabled_config)
                if not client.configured:
                    return ProviderTestOutcome(
                        ok=False,
                        detail="No web fetch API key is configured.",
                    )
                await client.fetch("https://example.com", max_chars=500)
            else:  # pragma: no cover - ProviderCapability is exhaustive.
                return ProviderTestOutcome(ok=False, detail="Unknown capability.")
        except Exception as exc:  # A connection failure must return a result, never a 500.
            logger.warning("Provider test failed for %s: %s", capability, exc)
            return ProviderTestOutcome(
                ok=False,
                detail=str(exc) or "The provider request failed.",
            )
        return ProviderTestOutcome(ok=True, detail="Connected.")


__all__ = [
    "NullWebClient",
    "ProviderClientTester",
    "ProviderFactory",
    "provider_defaults_from_settings",
]
