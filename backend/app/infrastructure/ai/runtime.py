"""Resolved AI provider runtime, refreshed when settings change."""

import logging

from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.embedding.http_embedder import DisabledEmbedder
from app.infrastructure.security.secret_cipher import SecretCipherError
from app.module.knowledge.domain.provider_config_domain import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CAPABILITY_WEB_FETCH,
    CAPABILITY_WEB_SEARCH,
    PROVIDER_TABLE_SPECS,
    ProviderCapability,
    ProviderTableSpec,
)
from app.module.knowledge.model.provider_config_model import ProviderConfigMixin
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_builder_protocol import (
    ProviderBuilderProtocol,
    WebClientProtocol,
)
from app.module.knowledge.protocol.provider_config import (
    ProviderConfig,
    ProviderDefaults,
    ProviderSnapshot,
)
from app.module.knowledge.protocol.provider_config_repository_protocol import (
    ProviderConfigRepositoryProtocol,
)
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
        self.web_search_client: WebClientProtocol = builder.build_web_client(
            self._default_web(CAPABILITY_WEB_SEARCH)
        )
        self.web_fetch_client: WebClientProtocol = builder.build_web_client(
            self._default_web(CAPABILITY_WEB_FETCH)
        )
        self.chat_config = self._default_chat()
        self.embedding_config = self._default_embedding()
        self.web_search_config = self._default_web(CAPABILITY_WEB_SEARCH)
        self.web_fetch_config = self._default_web(CAPABILITY_WEB_FETCH)

    def _default_chat(self) -> ProviderConfig:
        key = self.defaults.chat_api_key
        provider = self.defaults.chat_provider
        return ProviderConfig(
            capability=CAPABILITY_CHAT,
            provider=provider,
            label=provider,
            model=self.defaults.chat_model,
            base_url=self.defaults.chat_base_url,
            api_key=key,
            dimension=None,
            enabled=provider != "none" and bool(key),
            source="environment" if key else "default",
        )

    def _default_embedding(self) -> ProviderConfig:
        provider = self.defaults.embedding_provider
        key = self.defaults.embedding_api_key
        return ProviderConfig(
            capability=CAPABILITY_EMBEDDING,
            provider=provider,
            label=provider,
            model=self.defaults.embedding_model,
            base_url=self.defaults.embedding_base_url,
            api_key=key,
            dimension=self.defaults.embedding_dimension,
            enabled=provider != "none",
            source="default" if provider in {"hashing", "none"} else "environment",
        )

    def _default_web(self, capability: ProviderCapability) -> ProviderConfig:
        if capability == CAPABILITY_WEB_SEARCH:
            provider = self.defaults.web_search_provider
            base_url = self.defaults.web_search_base_url
            key = self.defaults.web_search_api_key
        else:
            provider = self.defaults.web_fetch_provider
            base_url = self.defaults.web_fetch_base_url
            key = self.defaults.web_fetch_api_key
        enabled = provider != "none" and bool(key)
        return ProviderConfig(
            capability=capability,
            provider=provider,
            label=provider,
            model=None,
            base_url=base_url if provider != "none" else None,
            api_key=key,
            dimension=None,
            enabled=enabled,
            source="environment" if key else "default",
        )

    def _decrypt_key(self, row: ProviderConfigMixin) -> str | None:
        if not row.api_key_ciphertext:
            return None
        try:
            return self.cipher.decrypt(row.api_key_ciphertext)
        except SecretCipherError as exc:
            logger.error(
                "Could not decrypt the %s API key; the provider is disabled until it is replaced.",
                row.provider,
            )
            logger.debug("Secret decryption detail: %s", exc)
            return None

    def _row_config(
        self,
        spec: ProviderTableSpec,
        row: ProviderConfigMixin,
    ) -> ProviderConfig:
        key = self._decrypt_key(row)
        # DB 金鑰優先；若該列沒有金鑰（或解密失敗），才回退到環境變數。
        # 這是 plan 4.2 的 fallback 規則，web_search / web_fetch 各自獨立解析。
        if key is None:
            key = self._environment_key(spec.capability)
        return ProviderConfig(
            capability=spec.capability,
            provider=row.provider,
            label=row.label or row.provider,
            model=row.model,
            base_url=row.base_url,
            api_key=key,
            dimension=row.dimension,
            enabled=row.is_active,
            source="database",
        )

    def _environment_key(self, capability: ProviderCapability) -> str | None:
        if capability == CAPABILITY_CHAT:
            return self.defaults.chat_api_key
        if capability == CAPABILITY_EMBEDDING:
            return self.defaults.embedding_api_key
        if capability == CAPABILITY_WEB_SEARCH:
            return self.defaults.web_search_api_key
        return self.defaults.web_fetch_api_key

    async def reload(self, repository: ProviderConfigRepositoryProtocol) -> None:
        """Reload the four capability slots from the database.

        每個 capability 最多一列 active（partial unique index 保證），所以這裡
        固定四張表各查一次；不用 union，避免 active 語意模糊。
        """
        configs: dict[ProviderCapability, ProviderConfig] = {
            CAPABILITY_CHAT: self._default_chat(),
            CAPABILITY_EMBEDDING: self._default_embedding(),
            CAPABILITY_WEB_SEARCH: self._default_web(CAPABILITY_WEB_SEARCH),
            CAPABILITY_WEB_FETCH: self._default_web(CAPABILITY_WEB_FETCH),
        }
        for spec in PROVIDER_TABLE_SPECS.values():
            row = await repository.get_active(spec)
            if row is not None:
                configs[spec.capability] = self._row_config(spec, row)

        snapshot = ProviderSnapshot(
            chat=configs[CAPABILITY_CHAT],
            embedding=configs[CAPABILITY_EMBEDDING],
            web_search=configs[CAPABILITY_WEB_SEARCH],
            web_fetch=configs[CAPABILITY_WEB_FETCH],
        )
        self.chat_config = snapshot.chat
        self.embedding_config = snapshot.embedding
        self.web_search_config = snapshot.web_search
        self.web_fetch_config = snapshot.web_fetch
        self.text_generator = self.builder.build_text_generator(snapshot.chat)
        self.embedder = self.builder.build_embedder(snapshot.embedding)
        self.web_search_client = self.builder.build_web_client(snapshot.web_search)
        self.web_fetch_client = self.builder.build_web_client(snapshot.web_fetch)

    @property
    def vector_enabled(self) -> bool:
        return self.embedder.dimension > 0
