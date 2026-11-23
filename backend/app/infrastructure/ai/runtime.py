"""Resolved AI provider runtime, refreshed when settings change."""

import asyncio
import logging

from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.ai.fallbacks import (
    FallbackEmbedder,
    FallbackTextGenerator,
    FallbackWebClient,
)
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
from app.module.knowledge.protocol.provider_notice_protocol import ProviderFailureReporter
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
        reporter: ProviderFailureReporter | None = None,
    ) -> None:
        self.builder = builder
        self.cipher = cipher
        self.defaults = defaults
        # The reporter is optional so unit tests and embedders that build a
        # runtime without a database keep working. Production always injects the
        # persistent provider-error notice service.
        self.reporter = reporter
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
        # Seed the chains from the environment/default snapshot so the first
        # database reload reports "unchanged" when the database is empty.
        self.chat_chain: tuple[ProviderConfig, ...] = (
            (self.chat_config,) if self.chat_config.enabled else ()
        )
        self.embedding_chain: tuple[ProviderConfig, ...] = (
            (self.embedding_config,) if self.embedding_config.enabled else ()
        )
        self.web_search_chain: tuple[ProviderConfig, ...] = (
            (self.web_search_config,) if self.web_search_config.enabled else ()
        )
        self.web_fetch_chain: tuple[ProviderConfig, ...] = (
            (self.web_fetch_config,) if self.web_fetch_config.enabled else ()
        )
        # The API and a worker may both refresh the runtime. Serializing reloads
        # keeps each snapshot internally consistent and makes the change
        # comparison below reliable.
        self._reload_lock = asyncio.Lock()

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
        """Decrypt one stored key; a failure stays keyless, never env-backed.

        The caller distinguishes "no ciphertext" from "failed to decrypt" by
        checking ``row.api_key_ciphertext`` itself. A stored ciphertext that no
        longer decrypts must not borrow another secret from the environment.
        """
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
        if not row.api_key_ciphertext:
            # Environment enrichment is row enrichment, not a global fallback.
            # It applies only to a row with no stored ciphertext at all, and the
            # provider-aware lookup guarantees an Anthropic row can never receive
            # the DeepSeek deployment key. A failed decryption above stays
            # keyless so a corrupted key is visible instead of silently hidden.
            key = self._environment_key(spec.capability, row.provider)
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
            row_id=row.id,
            # Reasoning effort is per-account, not per-row: the shared endpoint
            # row has no effort column. The per-user resolver fills it with
            # ``model_copy(update={"reasoning_effort": ...})``.
            reasoning_effort=None,
            max_output_tokens=getattr(row, "max_output_tokens", None),
        )

    def _environment_key(
        self,
        capability: ProviderCapability,
        provider: str,
    ) -> str | None:
        if capability == CAPABILITY_CHAT:
            # Chat keys are provider-specific. Returning the deployment's
            # DeepSeek key for an Anthropic row would silently bill the wrong
            # endpoint, so an unrecognised chat provider gets no environment key.
            if provider == "anthropic":
                return self.defaults.anthropic_api_key
            if provider == "deepseek":
                return self.defaults.deepseek_api_key
            return None
        if capability == CAPABILITY_EMBEDDING:
            return self.defaults.embedding_api_key
        if provider == "exa":
            return self.defaults.exa_api_key
        if provider == "tavily":
            return self.defaults.tavily_api_key
        if provider == "deepseek":
            return self.defaults.deepseek_api_key
        if capability == CAPABILITY_WEB_SEARCH:
            return self.defaults.web_search_api_key
        return self.defaults.web_fetch_api_key

    async def reload(
        self,
        repository: ProviderConfigRepositoryProtocol,
        *,
        announce: bool = True,
    ) -> bool:
        """Reload the four ordered capability chains from the database.

        Each table may contain several active rows. They are loaded in
        ``(priority, id)`` order, so index 0 is the primary and later entries are
        backups. With no active rows, the environment/default configuration is
        used only when it is enabled; otherwise the chain stays empty and the
        runtime exposes the disabled/null clients as before.

        ``announce`` is true for startup and for the root write path, which
        should always log the loaded snapshot. The worker's routine
        batch-boundary refresh passes ``announce=False`` so an unchanged
        snapshot logs at DEBUG and only an effective configuration change
        (including a rotated key, a new base URL, model, dimension, or chain
        order) reaches INFO. The return value reports whether the effective
        snapshot changed.
        """
        async with self._reload_lock:
            previous = self._snapshot()
            defaults: dict[ProviderCapability, ProviderConfig] = {
                CAPABILITY_CHAT: self._default_chat(),
                CAPABILITY_EMBEDDING: self._default_embedding(),
                CAPABILITY_WEB_SEARCH: self._default_web(CAPABILITY_WEB_SEARCH),
                CAPABILITY_WEB_FETCH: self._default_web(CAPABILITY_WEB_FETCH),
            }
            chains: dict[ProviderCapability, tuple[ProviderConfig, ...]] = {}
            for spec in PROVIDER_TABLE_SPECS.values():
                rows = await repository.list_active_chain(spec)
                if rows:
                    chains[spec.capability] = tuple(
                        self._row_config(spec, row) for row in rows
                    )
                    continue
                fallback = defaults[spec.capability]
                chains[spec.capability] = (fallback,) if fallback.enabled else ()

            configs = {
                capability: chain[0] if chain else defaults[capability]
                for capability, chain in chains.items()
            }
            snapshot = ProviderSnapshot(
                chat=configs[CAPABILITY_CHAT],
                embedding=configs[CAPABILITY_EMBEDDING],
                web_search=configs[CAPABILITY_WEB_SEARCH],
                web_fetch=configs[CAPABILITY_WEB_FETCH],
                chat_chain=chains[CAPABILITY_CHAT],
                embedding_chain=chains[CAPABILITY_EMBEDDING],
                web_search_chain=chains[CAPABILITY_WEB_SEARCH],
                web_fetch_chain=chains[CAPABILITY_WEB_FETCH],
            )
            changed = snapshot != previous
            self._apply_snapshot(snapshot)
            if announce or changed:
                self._log_snapshot(snapshot, logging.INFO)
            else:
                logger.debug(
                    "provider runtime unchanged embedding_provider=%s embedding_model=%s "
                    "embedding_dimension=%s chat_chain=%s embedding_chain=%s",
                    snapshot.embedding.provider,
                    snapshot.embedding.model or "-",
                    snapshot.embedding.dimension,
                    _chain_label(snapshot.chat_chain),
                    _chain_label(snapshot.embedding_chain),
                )
            return changed

    def _apply_snapshot(self, snapshot: ProviderSnapshot) -> None:
        """Publish one snapshot and rebuild every client/wrapper together."""
        self.chat_config = snapshot.chat
        self.embedding_config = snapshot.embedding
        self.web_search_config = snapshot.web_search
        self.web_fetch_config = snapshot.web_fetch
        self.chat_chain = snapshot.chat_chain
        self.embedding_chain = snapshot.embedding_chain
        self.web_search_chain = snapshot.web_search_chain
        self.web_fetch_chain = snapshot.web_fetch_chain

        chat_entries = [
            (config.provider, self.builder.build_text_generator(config))
            for config in snapshot.chat_chain
        ]
        if len(chat_entries) > 1:
            self.text_generator = FallbackTextGenerator(
                chat_entries,
                reporter=self.reporter,
            )
        elif chat_entries:
            self.text_generator = chat_entries[0][1]
        else:
            self.text_generator = NullTextGenerator()

        embedding_entries = [
            (config.provider, self.builder.build_embedder(config))
            for config in snapshot.embedding_chain
        ]
        if len(embedding_entries) > 1:
            self.embedder = FallbackEmbedder(
                embedding_entries,
                reporter=self.reporter,
            )
        elif embedding_entries:
            self.embedder = embedding_entries[0][1]
        else:
            self.embedder = DisabledEmbedder()

        self.web_search_client = self._build_web_client_or_fallback(
            CAPABILITY_WEB_SEARCH,
            snapshot.web_search_chain,
        )
        self.web_fetch_client = self._build_web_client_or_fallback(
            CAPABILITY_WEB_FETCH,
            snapshot.web_fetch_chain,
        )

    def _build_web_client_or_fallback(
        self,
        capability: ProviderCapability,
        chain: tuple[ProviderConfig, ...],
    ) -> WebClientProtocol:
        entries = [
            (config.provider, self.builder.build_web_client(config))
            for config in chain
        ]
        if len(entries) > 1:
            return FallbackWebClient(
                entries,
                capability=capability,
                reporter=self.reporter,
            )
        if entries:
            return entries[0][1]
        return self.builder.build_web_client(
            self._default_web(capability),
        )

    def _snapshot(self) -> ProviderSnapshot:
        """Capture the currently resolved capability slots and chains."""
        return ProviderSnapshot(
            chat=self.chat_config,
            embedding=self.embedding_config,
            web_search=self.web_search_config,
            web_fetch=self.web_fetch_config,
            chat_chain=self.chat_chain,
            embedding_chain=self.embedding_chain,
            web_search_chain=self.web_search_chain,
            web_fetch_chain=self.web_fetch_chain,
        )

    @staticmethod
    def _log_snapshot(snapshot: ProviderSnapshot, level: int) -> None:
        """Log the safe parts of one snapshot; the key is reduced to presence."""
        logger.log(
            level,
            "provider runtime loaded chat_provider=%s chat_model=%s "
            "chat_base_url=%s chat_source=%s chat_enabled=%s chat_key=%s "
            "chat_chain=%s "
            "embedding_provider=%s embedding_model=%s embedding_dimension=%s "
            "embedding_source=%s embedding_chain=%s "
            "web_search_provider=%s web_search_chain=%s "
            "web_fetch_provider=%s web_fetch_chain=%s",
            snapshot.chat.provider,
            snapshot.chat.model or "-",
            snapshot.chat.base_url or "-",
            snapshot.chat.source,
            snapshot.chat.enabled,
            "present" if snapshot.chat.api_key else "missing",
            _chain_label(snapshot.chat_chain),
            snapshot.embedding.provider,
            snapshot.embedding.model or "-",
            snapshot.embedding.dimension,
            snapshot.embedding.source,
            _chain_label(snapshot.embedding_chain),
            snapshot.web_search.provider,
            _chain_label(snapshot.web_search_chain),
            snapshot.web_fetch.provider,
            _chain_label(snapshot.web_fetch_chain),
        )

    @property
    def vector_enabled(self) -> bool:
        return self.embedder.dimension > 0


def _chain_label(chain: tuple[ProviderConfig, ...]) -> str:
    """Render provider names in order without any credential material."""
    if not chain:
        return "none"
    return "->".join(config.provider for config in chain)
