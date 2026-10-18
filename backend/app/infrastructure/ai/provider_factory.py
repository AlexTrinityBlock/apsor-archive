"""Build chat and embedding clients from resolved provider configuration."""

from app.infrastructure.ai.deepseek_client import DeepSeekClient, NullTextGenerator
from app.infrastructure.config.settings import Settings
from app.infrastructure.embedding.http_embedder import (
    DisabledEmbedder,
    OpenAICompatibleEmbedder,
)
from app.module.knowledge.domain.hashing_embedder import HashingEmbedder
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_config import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    ProviderConfig,
    ProviderDefaults,
)
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol


def provider_defaults_from_settings(settings: Settings) -> ProviderDefaults:
    """Project environment settings into the provider runtime defaults."""
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
    )


class ProviderFactory:
    """The only place that turns configuration into concrete clients."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_text_generator(self, config: ProviderConfig) -> TextGeneratorProtocol:
        if (
            not config.enabled
            or config.provider not in CHAT_PROVIDERS
            or config.provider == "none"
            or not config.api_key
        ):
            return NullTextGenerator()
        return DeepSeekClient(
            api_key=config.api_key,
            base_url=config.base_url or self.settings.deepseek_base_url,
            model=config.model,
            timeout_seconds=self.settings.deepseek_timeout_seconds,
            max_tokens=self.settings.deepseek_max_tokens,
            temperature=self.settings.deepseek_temperature,
            supports_thinking=config.provider == "deepseek",
        )

    def build_embedder(self, config: ProviderConfig) -> EmbedderProtocol:
        if not config.enabled or config.provider not in EMBEDDING_PROVIDERS:
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
            model=config.model,
            dimension=config.dimension or self.settings.embedding_dimension,
            timeout_seconds=self.settings.embedding_timeout_seconds,
        )
