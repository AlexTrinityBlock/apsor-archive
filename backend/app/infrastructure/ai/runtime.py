"""Resolved AI provider runtime, refreshed when settings change."""

import logging

from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.embedding.http_embedder import DisabledEmbedder
from app.infrastructure.security.secret_cipher import SecretCipherError
from app.module.knowledge.model.ai_config_model import (
    PURPOSE_CHAT,
    PURPOSE_EMBEDDING,
    AiProviderConfigModel,
)
from app.module.knowledge.protocol.ai_config_repository_protocol import (
    AiConfigRepositoryProtocol,
)
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_builder_protocol import ProviderBuilderProtocol
from app.module.knowledge.protocol.provider_config import ProviderConfig, ProviderDefaults
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol

logger = logging.getLogger(__name__)


class AiRuntime:
    """Hold the active clients and their safe configuration state."""

    def __init__(
        self,
        *,
        builder: ProviderBuilderProtocol,
        cipher: SecretCipherProtocol,
        defaults: ProviderDefaults,
    ) -> None:
        self.builder = builder
        self.cipher = cipher
        self.defaults = defaults
        self.text_generator: TextGeneratorProtocol = NullTextGenerator()
        self.embedder: EmbedderProtocol = DisabledEmbedder()
        self.chat_config = self._default_chat()
        self.embedding_config = self._default_embedding()

    def _default_chat(self) -> ProviderConfig:
        key = self.defaults.chat_api_key
        return ProviderConfig(
            purpose=PURPOSE_CHAT,
            provider=self.defaults.chat_provider,
            model=self.defaults.chat_model,
            base_url=self.defaults.chat_base_url,
            api_key=key,
            dimension=None,
            enabled=bool(key),
            source="environment" if key else "default",
        )

    def _default_embedding(self) -> ProviderConfig:
        provider = self.defaults.embedding_provider
        key = self.defaults.embedding_api_key
        return ProviderConfig(
            purpose=PURPOSE_EMBEDDING,
            provider=provider,
            model=self.defaults.embedding_model,
            base_url=self.defaults.embedding_base_url,
            api_key=key,
            dimension=self.defaults.embedding_dimension,
            enabled=provider != "none",
            source="default" if provider in {"hashing", "none"} else "environment",
        )

    def _decrypt_key(self, row: AiProviderConfigModel) -> str | None:
        if not row.api_key_ciphertext:
            return None
        try:
            return self.cipher.decrypt(row.api_key_ciphertext)
        except SecretCipherError as exc:
            logger.error(
                "Could not decrypt the %s API key; the provider is disabled until it is replaced.",
                row.purpose,
            )
            logger.debug("Secret decryption detail: %s", exc)
            return None

    def _row_config(self, row: AiProviderConfigModel) -> ProviderConfig:
        key = self._decrypt_key(row)
        if key is None and row.purpose == PURPOSE_CHAT:
            key = self.defaults.chat_api_key
        if key is None and row.purpose == PURPOSE_EMBEDDING:
            key = self.defaults.embedding_api_key
        return ProviderConfig(
            purpose=row.purpose,  # type: ignore[arg-type]
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            api_key=key,
            dimension=row.dimension,
            enabled=row.enabled,
            source="database",
        )

    async def reload(self, repository: AiConfigRepositoryProtocol) -> None:
        """Reload both provider slots from the database."""
        rows = {row.purpose: row for row in await repository.list_all()}
        chat_row = rows.get(PURPOSE_CHAT)
        embedding_row = rows.get(PURPOSE_EMBEDDING)
        self.chat_config = (
            self._row_config(chat_row) if chat_row is not None else self._default_chat()
        )
        self.embedding_config = (
            self._row_config(embedding_row)
            if embedding_row is not None
            else self._default_embedding()
        )
        self.text_generator = self.builder.build_text_generator(self.chat_config)
        self.embedder = self.builder.build_embedder(self.embedding_config)

    @property
    def vector_enabled(self) -> bool:
        return self.embedder.dimension > 0
