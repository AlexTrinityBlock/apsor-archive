"""Generic CRUD, validation, caching, and connection tests for providers.

One service instance drives all four capabilities.  The only capability-specific
branches are validation rules and the runtime slot used to report readiness.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from app.infrastructure.security.secret_cipher import SecretCipherError
from app.module.knowledge.domain.provider_config_domain import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CAPABILITY_WEB_SEARCH,
    PROVIDER_CAPABILITIES,
    PROVIDER_TABLE_SPECS,
    ProviderCapability,
    ProviderTableSpec,
)
from app.module.knowledge.exception.domain_error import (
    EmbeddingProviderError,
    InvalidProviderConfigError,
    ProviderNotFoundError,
)
from app.module.knowledge.model.provider_config_model import ProviderConfigMixin
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.provider_config import ProviderConfig, ProviderDefaults
from app.module.knowledge.protocol.provider_config_repository_protocol import (
    ProviderConfigRepositoryProtocol,
)
from app.module.knowledge.protocol.provider_runtime_protocol import ProviderRuntimeProtocol
from app.module.knowledge.protocol.provider_tester_protocol import ProviderTesterProtocol
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.schema.provider_config_schema import (
    KeySource,
    ProviderCapabilityReadSchema,
    ProviderCreateSchema,
    ProviderReadSchema,
    ProviderRegistryReadSchema,
    ProviderTestResultSchema,
    ProviderUpdateSchema,
)
from app.module.knowledge.schema.settings_schema import EmbeddingReindexSchema
from app.module.knowledge.service.cache_keys import cache_key
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

REGISTRY_CACHE_TTL_SECONDS = 30
PROVIDERS_CACHE_SCOPE = "providers"


@dataclass(frozen=True)
class _NormalizedProvider:
    """A validated payload after trimming and defaulting."""

    provider: str
    label: str
    model: str | None
    base_url: str | None
    dimension: int | None


class ProviderConfigService:
    """Read and mutate the provider registry without ever returning a key."""

    def __init__(
        self,
        *,
        repository: ProviderConfigRepositoryProtocol,
        runtime: ProviderRuntimeProtocol,
        cipher: SecretCipherProtocol,
        defaults: ProviderDefaults,
        chunk_repository: ChunkRepositoryProtocol,
        cache: CacheProtocol,
        tester: ProviderTesterProtocol,
        registry_ttl_seconds: int = REGISTRY_CACHE_TTL_SECONDS,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.cipher = cipher
        self.defaults = defaults
        self.chunk_repository = chunk_repository
        self.cache = cache
        self.tester = tester
        self.registry_ttl_seconds = registry_ttl_seconds

    # ------------------------------------------------------------------
    # Registry reads
    # ------------------------------------------------------------------

    async def get_registry(self) -> ProviderRegistryReadSchema:
        """Return the cached registry, rebuilding it after any provider write."""
        version = await self.cache.get_version(PROVIDERS_CACHE_SCOPE)
        key = cache_key(version, "provider_registry")
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return ProviderRegistryReadSchema.model_validate(cached)

        capabilities: list[ProviderCapabilityReadSchema] = []
        for capability in PROVIDER_CAPABILITIES:
            spec = PROVIDER_TABLE_SPECS[capability]
            rows = list(await self.repository.list_all(spec))
            reads = [self._read_saved(spec, row) for row in rows]
            active_row = next((row for row in rows if row.is_active), None)
            active = (
                self._read_active(spec, active_row)
                if active_row is not None
                else self._read_virtual_active(spec)
            )
            capabilities.append(
                ProviderCapabilityReadSchema(
                    capability=capability,
                    title=spec.title,
                    description=spec.description,
                    allowed_providers=sorted(spec.allowed_providers),
                    keyless_providers=sorted(spec.keyless_providers),
                    default_base_url=spec.default_base_url,
                    supports_model=spec.supports_model,
                    supports_dimension=spec.supports_dimension,
                    active=active,
                    providers=reads,
                )
            )

        registry = ProviderRegistryReadSchema(
            capabilities=capabilities,
            vector_enabled=self.runtime.vector_enabled,
            reindex_required=await self._reindex_required(),
        )
        await self.cache.set_json(
            key,
            registry.model_dump(mode="json"),
            self.registry_ttl_seconds,
        )
        return registry

    def _read_saved(
        self,
        spec: ProviderTableSpec,
        row: ProviderConfigMixin,
    ) -> ProviderReadSchema:
        return ProviderReadSchema(
            id=row.id,
            capability=spec.capability,
            provider=row.provider,
            label=row.label or row.provider,
            model=row.model,
            base_url=row.base_url,
            dimension=row.dimension,
            is_active=row.is_active,
            configured=self._row_configured(spec, row),
            key_hint=row.api_key_hint,
            key_source="database" if row.api_key_ciphertext else "none",
            source="database",
            updated_at=row.updated_at,
        )

    def _read_active(
        self,
        spec: ProviderTableSpec,
        row: ProviderConfigMixin,
    ) -> ProviderReadSchema:
        """Read an active row, including any environment key fallback."""
        config = self._current_config(spec)
        key_source: KeySource = "none"
        if row.api_key_ciphertext:
            key_source = "database"
        elif config.api_key:
            key_source = "environment"
        hint = row.api_key_hint
        if hint is None and key_source == "environment" and config.api_key:
            hint = self.cipher.hint(config.api_key)
        return ProviderReadSchema(
            id=row.id,
            capability=spec.capability,
            provider=row.provider,
            label=row.label or row.provider,
            model=row.model,
            base_url=row.base_url,
            dimension=row.dimension,
            is_active=True,
            configured=self._active_configured(spec),
            key_hint=hint,
            key_source=key_source,
            source="database",
            updated_at=row.updated_at,
        )

    def _read_virtual_active(self, spec: ProviderTableSpec) -> ProviderReadSchema:
        """Describe the environment/default fallback when no row is active."""
        config = self._current_config(spec)
        return ProviderReadSchema(
            id=None,
            capability=spec.capability,
            provider=config.provider,
            label=config.label or config.provider,
            model=config.model,
            base_url=config.base_url,
            dimension=config.dimension,
            is_active=config.enabled,
            configured=self._active_configured(spec),
            key_hint=self.cipher.hint(config.api_key) if config.api_key else None,
            key_source="environment" if config.api_key else "none",
            source=config.source,
            updated_at=None,
        )

    def _current_config(self, spec: ProviderTableSpec) -> ProviderConfig:
        if spec.capability == CAPABILITY_CHAT:
            return self.runtime.chat_config
        if spec.capability == CAPABILITY_EMBEDDING:
            return self.runtime.embedding_config
        if spec.capability == CAPABILITY_WEB_SEARCH:
            return self.runtime.web_search_config
        return self.runtime.web_fetch_config

    def _active_configured(self, spec: ProviderTableSpec) -> bool:
        if spec.capability == CAPABILITY_CHAT:
            return self.runtime.text_generator.configured
        if spec.capability == CAPABILITY_EMBEDDING:
            return self.runtime.embedder.dimension > 0
        if spec.capability == CAPABILITY_WEB_SEARCH:
            return self.runtime.web_search_client.configured
        return self.runtime.web_fetch_client.configured

    @staticmethod
    def _row_configured(spec: ProviderTableSpec, row: ProviderConfigMixin) -> bool:
        if row.provider == "none":
            return False
        if row.provider in spec.keyless_providers:
            return True
        return bool(row.api_key_ciphertext)

    async def _reindex_required(self) -> bool:
        if self.runtime.embedder.dimension <= 0:
            return False
        counts = await self.chunk_repository.embedding_model_counts()
        current_model = self.runtime.embedder.model_name
        return any(model != current_model for model in counts)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create(
        self,
        capability: str,
        payload: ProviderCreateSchema,
    ) -> ProviderRegistryReadSchema:
        spec = self._spec(capability)
        normalized = self._validate(spec, payload)
        now = utcnow()
        # mixin 沒有帶型別的 __init__；concrete declarative class 接受這些
        # mapped-column keyword。cast 只是把這個形狀告訴 mypy。
        model_factory = cast(type[Any], spec.model)
        row: ProviderConfigMixin = model_factory(
            provider=normalized.provider,
            label=normalized.label,
            model=normalized.model,
            base_url=normalized.base_url,
            dimension=normalized.dimension,
            is_active=False,
            created_at=now,
            updated_at=now,
        )
        self._apply_key(
            row=row,
            payload=payload,
            keyless=normalized.provider in spec.keyless_providers,
        )
        # 先存檔取得 identity id；partial unique index 允許任意多列 inactive，
        # 所以順序必須是「先 insert inactive，再 deactivate 其他列，最後設 active」。
        await self.repository.save(row)
        if payload.activate:
            await self.repository.deactivate_others(spec, keep_id=row.id)
            row.is_active = True
            row.updated_at = utcnow()
        await self._after_write(spec)
        return await self.get_registry()

    async def update(
        self,
        capability: str,
        provider_id: int,
        payload: ProviderUpdateSchema,
    ) -> ProviderRegistryReadSchema:
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        normalized = self._validate(spec, payload)
        row.provider = normalized.provider
        row.label = normalized.label
        row.model = normalized.model
        row.base_url = normalized.base_url
        row.dimension = normalized.dimension
        row.updated_at = utcnow()
        self._apply_key(
            row=row,
            payload=payload,
            keyless=normalized.provider in spec.keyless_providers,
        )
        if payload.activate:
            await self.repository.deactivate_others(spec, keep_id=row.id)
            row.is_active = True
        # activate=False keeps the row's current active state; deactivation is a
        # separate explicit endpoint so an edit cannot silently drop a capability.
        await self.repository.save(row)
        await self._after_write(spec)
        return await self.get_registry()

    async def delete(
        self,
        capability: str,
        provider_id: int,
    ) -> ProviderRegistryReadSchema:
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        if row.is_active:
            # Deactivate before deleting so the capability immediately falls
            # back to environment/default until the transaction commits.
            await self.repository.deactivate_all(spec)
        await self.repository.delete(row)
        await self._after_write(spec)
        return await self.get_registry()

    async def activate(
        self,
        capability: str,
        provider_id: int,
    ) -> ProviderRegistryReadSchema:
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        await self.repository.deactivate_others(spec, keep_id=row.id)
        row.is_active = True
        row.updated_at = utcnow()
        await self.repository.save(row)
        await self._after_write(spec)
        return await self.get_registry()

    async def deactivate(self, capability: str) -> ProviderRegistryReadSchema:
        """Clear the active row for one capability; runtime falls back."""
        spec = self._spec(capability)
        await self.repository.deactivate_all(spec)
        await self._after_write(spec)
        return await self.get_registry()

    async def _after_write(self, spec: ProviderTableSpec) -> None:
        """Flush, refresh the runtime, then invalidate the scoped caches."""
        await self.repository.flush()
        await self.runtime.reload(self.repository)
        # Provider 寫入只失效 providers scope 的 registry cache。Embedding 設定
        # 另外失效 default "index" scope，因為 search/timeline 的 cache key 都
        # 綁在 index version 上。
        await self.cache.bump_version(PROVIDERS_CACHE_SCOPE)
        if spec.capability == CAPABILITY_EMBEDDING:
            await self.cache.bump_version()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _spec(capability: str) -> ProviderTableSpec:
        if capability not in PROVIDER_TABLE_SPECS:
            raise InvalidProviderConfigError(
                f"capability must be one of {list(PROVIDER_CAPABILITIES)}."
            )
        return PROVIDER_TABLE_SPECS[capability]

    def _validate(
        self,
        spec: ProviderTableSpec,
        payload: ProviderCreateSchema | ProviderUpdateSchema,
    ) -> _NormalizedProvider:
        provider = payload.provider.strip().lower()
        if provider not in spec.allowed_providers:
            raise InvalidProviderConfigError(
                f"{spec.title} provider must be one of {sorted(spec.allowed_providers)}."
            )

        label = (payload.label or "").strip() or provider
        if len(label) > 80:
            raise InvalidProviderConfigError("label must be at most 80 characters.")

        base_url = self._validate_base_url(spec, provider, payload.base_url)
        raw_model = payload.model.strip() if payload.model is not None else None

        if spec.supports_model:
            if provider == "none":
                model = "none"
            elif not raw_model:
                raise InvalidProviderConfigError("model is required for this provider.")
            else:
                model = raw_model
            if len(model) > 128:
                raise InvalidProviderConfigError("model must be at most 128 characters.")
        else:
            if payload.model is not None:
                raise InvalidProviderConfigError("model must be null for web providers.")
            model = None

        if spec.supports_dimension:
            if provider == "none":
                dimension = None
            else:
                dimension = payload.dimension
        else:
            if payload.dimension is not None:
                raise InvalidProviderConfigError(
                    "dimension is only supported by the embedding capability."
                )
            dimension = None

        return _NormalizedProvider(
            provider=provider,
            label=label,
            model=model,
            base_url=base_url,
            dimension=dimension,
        )

    @staticmethod
    def _validate_base_url(
        spec: ProviderTableSpec,
        provider: str,
        value: str | None,
    ) -> str | None:
        """Normalize and validate an optional http(s) base URL."""
        raw = (value or "").strip()
        if not raw:
            if provider == "none" or provider == "hashing":
                return None
            if provider == "openai-compatible":
                raise InvalidProviderConfigError("openai-compatible providers require a base URL.")
            return spec.default_base_url
        if len(raw) > 500:
            raise InvalidProviderConfigError("base_url must be at most 500 characters.")
        if any(character.isspace() or ord(character) < 0x20 for character in raw):
            raise InvalidProviderConfigError(
                "base_url must not contain whitespace or control characters."
            )
        cleaned = raw.rstrip("/")
        parts = urlsplit(cleaned)
        if parts.scheme not in {"http", "https"} or not parts.netloc or not parts.hostname:
            raise InvalidProviderConfigError("base_url must be an absolute http or https URL.")
        if parts.username is not None or parts.password is not None:
            raise InvalidProviderConfigError("base_url must not contain credentials.")
        try:
            # Accessing .port validates the numeric range and rejects strings such
            # as "https://example.com:not-a-port" before they reach httpx.
            _ = parts.port
        except ValueError as exc:
            raise InvalidProviderConfigError("base_url has an invalid port.") from exc
        return cleaned

    def _apply_key(
        self,
        *,
        row: ProviderConfigMixin,
        payload: ProviderCreateSchema | ProviderUpdateSchema,
        keyless: bool,
    ) -> None:
        """Apply the key mutation rules without ever logging a plaintext key."""
        clear = bool(getattr(payload, "clear_api_key", False))
        if keyless:
            # Keyless providers never store a secret even if one is sent.
            row.api_key_ciphertext = None
            row.api_key_hint = None
            return
        if payload.api_key is not None:
            plaintext = payload.api_key.strip()
            if not plaintext:
                raise InvalidProviderConfigError(
                    "api_key must not be blank; use clear_api_key to remove it."
                )
            row.api_key_ciphertext = self.cipher.encrypt(plaintext)
            row.api_key_hint = self.cipher.hint(plaintext)
            return
        if clear:
            row.api_key_ciphertext = None
            row.api_key_hint = None

    # ------------------------------------------------------------------
    # Connection tests and re-indexing
    # ------------------------------------------------------------------

    async def test(
        self,
        capability: str,
        provider_id: int,
    ) -> ProviderTestResultSchema:
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        config = self._config_from_row(spec, row, force_enabled=True)
        started = time.perf_counter()
        # The tester seam keeps the real endpoint behaviour while allowing the
        # test suite to inject a deterministic fake (no external HTTP calls).
        outcome = await self.tester.test(spec.capability, config)
        return ProviderTestResultSchema(
            ok=outcome.ok,
            capability=spec.capability,
            provider_id=row.id,
            provider=row.provider,
            label=row.label or row.provider,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=outcome.detail,
        )

    async def reindex_embeddings(self) -> EmbeddingReindexSchema:
        """Re-embed every current chunk with the active embedding provider."""
        embedder = self.runtime.embedder
        if embedder.dimension <= 0:
            raise InvalidProviderConfigError("Embeddings are disabled.")
        started = time.perf_counter()
        offset = 0
        reindexed = 0
        batch_size = 64
        while True:
            chunks = await self.chunk_repository.list_current_chunks(
                limit=batch_size,
                offset=offset,
            )
            if not chunks:
                break
            vectors = await embedder.embed([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise EmbeddingProviderError(
                    f"The provider returned {len(vectors)} vectors for {len(chunks)} chunks."
                )
            for chunk, vector in zip(chunks, vectors, strict=True):
                await self.chunk_repository.update_embedding(
                    chunk.id,
                    vector,
                    embedder.model_name,
                )
            reindexed += len(chunks)
            offset += len(chunks)
        await self.cache.bump_version()
        return EmbeddingReindexSchema(
            reindexed=reindexed,
            model=embedder.model_name,
            dimension=embedder.dimension,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    # ------------------------------------------------------------------
    # Internal configuration helpers
    # ------------------------------------------------------------------

    async def get_active_client_config(
        self,
        capability: ProviderCapability,
    ) -> ProviderConfig:
        """Resolve one capability for server-side consumers (may contain a key).

        This method is intentionally not exposed through any router.  It is a
        safe internal seam for future consumers that need the decrypted config;
        the web-research tools read the same values from the runtime snapshot
        instead of opening a database session.
        """
        spec = self._spec(capability)
        row = await self.repository.get_active(spec)
        if row is None:
            return self._current_config(spec)
        return self._config_from_row(spec, row)

    def _config_from_row(
        self,
        spec: ProviderTableSpec,
        row: ProviderConfigMixin,
        *,
        force_enabled: bool = False,
    ) -> ProviderConfig:
        key = self._decrypt_key(row)
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
            enabled=force_enabled or row.is_active,
            source="database",
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

    def _environment_key(self, capability: ProviderCapability) -> str | None:
        if capability == CAPABILITY_CHAT:
            return self.defaults.chat_api_key
        if capability == CAPABILITY_EMBEDDING:
            return self.defaults.embedding_api_key
        if capability == CAPABILITY_WEB_SEARCH:
            return self.defaults.web_search_api_key
        return self.defaults.web_fetch_api_key


__all__ = ["ProviderConfigService"]
