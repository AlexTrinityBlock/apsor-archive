"""Database-backed AI provider settings and connection tests."""

import time
from datetime import UTC, datetime
from typing import cast

from app.infrastructure.ai.runtime import AiRuntime
from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    EmbeddingProviderError,
    InvalidProviderConfigError,
)
from app.module.knowledge.model.ai_config_model import (
    PURPOSE_CHAT,
    PURPOSE_EMBEDDING,
    AiProviderConfigModel,
)
from app.module.knowledge.protocol.ai_config_repository_protocol import (
    AiConfigRepositoryProtocol,
)
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.provider_config import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    KEYLESS_PROVIDERS,
    ProviderConfig,
    ProviderDefaults,
)
from app.module.knowledge.protocol.secret_cipher_protocol import SecretCipherProtocol
from app.module.knowledge.schema.settings_schema import (
    AiProviderReadSchema,
    AiProviderUpdateSchema,
    AiPurpose,
    AiSettingsReadSchema,
    AiTestResultSchema,
    EmbeddingReindexSchema,
)

PURPOSES = {PURPOSE_CHAT, PURPOSE_EMBEDDING}


class AiConfigService:
    """Read and update provider settings without ever returning a key."""

    def __init__(
        self,
        *,
        repository: AiConfigRepositoryProtocol,
        runtime: AiRuntime,
        cipher: SecretCipherProtocol,
        defaults: ProviderDefaults,
        chunk_repository: ChunkRepositoryProtocol,
        cache: CacheProtocol,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.cipher = cipher
        self.defaults = defaults
        self.chunk_repository = chunk_repository
        self.cache = cache

    @staticmethod
    def _purpose(value: str) -> AiPurpose:
        if value not in PURPOSES:
            raise InvalidProviderConfigError("purpose must be 'chat' or 'embedding'.")
        return cast(AiPurpose, value)

    def _read(
        self,
        purpose: AiPurpose,
        config: ProviderConfig,
        row: AiProviderConfigModel | None,
    ) -> AiProviderReadSchema:
        configured = (
            self.runtime.text_generator.configured
            if purpose == PURPOSE_CHAT
            else self.runtime.embedder.dimension > 0
        )
        hint = row.api_key_hint if row is not None else None
        key_source = "database" if row is not None and row.api_key_ciphertext else "none"
        if hint is None and config.api_key:
            hint = self.cipher.hint(config.api_key)
        if key_source == "none" and config.api_key:
            key_source = "environment"
        return AiProviderReadSchema(
            purpose=purpose,
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            dimension=config.dimension,
            enabled=config.enabled,
            configured=configured,
            key_hint=hint,
            key_source=key_source,  # type: ignore[arg-type]
            source=config.source,
            updated_at=row.updated_at if row is not None else None,
        )

    async def _reindex_required(self) -> bool:
        if self.runtime.embedder.dimension <= 0:
            return False
        counts = await self.chunk_repository.embedding_model_counts()
        current_model = self.runtime.embedder.model_name
        return any(model != current_model for model in counts)

    async def get_settings(self) -> AiSettingsReadSchema:
        rows = {row.purpose: row for row in await self.repository.list_all()}
        return AiSettingsReadSchema(
            chat=self._read(
                PURPOSE_CHAT,
                self.runtime.chat_config,
                rows.get(PURPOSE_CHAT),
            ),
            embedding=self._read(
                PURPOSE_EMBEDDING,
                self.runtime.embedding_config,
                rows.get(PURPOSE_EMBEDDING),
            ),
            vector_enabled=self.runtime.vector_enabled,
            reindex_required=await self._reindex_required(),
        )

    def _validate(
        self,
        purpose: AiPurpose,
        payload: AiProviderUpdateSchema,
    ) -> tuple[str, str | None, int | None]:
        provider = payload.provider.strip().lower()
        if purpose == PURPOSE_CHAT and provider not in CHAT_PROVIDERS:
            raise InvalidProviderConfigError(
                f"Chat provider must be one of {sorted(CHAT_PROVIDERS)}."
            )
        if purpose == PURPOSE_EMBEDDING and provider not in EMBEDDING_PROVIDERS:
            raise InvalidProviderConfigError(
                f"Embedding provider must be one of {sorted(EMBEDDING_PROVIDERS)}."
            )
        base_url = payload.base_url.strip() if payload.base_url else None
        if provider in {"openai-compatible"} and not base_url:
            raise InvalidProviderConfigError(
                "openai-compatible providers require a base URL."
            )
        if purpose == PURPOSE_CHAT:
            return provider, base_url, None
        if provider == "hashing":
            return provider, base_url, payload.dimension or 384
        if provider in {"openai", "openai-compatible"}:
            return provider, base_url, payload.dimension or self.defaults.embedding_dimension
        return provider, base_url, None

    def _apply_key(
        self,
        *,
        row: AiProviderConfigModel,
        payload: AiProviderUpdateSchema,
        provider: str,
    ) -> None:
        if provider in KEYLESS_PROVIDERS or payload.clear_api_key:
            row.api_key_ciphertext = None
            row.api_key_hint = None
            return
        if payload.api_key is None:
            return
        plaintext = payload.api_key.strip()
        if not plaintext:
            raise InvalidProviderConfigError(
                "api_key must not be blank; use clear_api_key to remove it."
            )
        row.api_key_ciphertext = self.cipher.encrypt(plaintext)
        row.api_key_hint = self.cipher.hint(plaintext)

    async def update(
        self,
        purpose_value: str,
        payload: AiProviderUpdateSchema,
    ) -> AiSettingsReadSchema:
        purpose = self._purpose(purpose_value)
        provider, base_url, dimension = self._validate(purpose, payload)
        row = await self.repository.get_by_purpose(purpose)
        now = datetime.now(UTC)
        if row is None:
            row = AiProviderConfigModel(
                purpose=purpose,
                provider=provider,
                model=payload.model.strip(),
                base_url=base_url,
                dimension=dimension,
                enabled=payload.enabled,
                created_at=now,
                updated_at=now,
            )
        else:
            row.provider = provider
            row.model = payload.model.strip()
            row.base_url = base_url
            row.dimension = dimension
            row.enabled = payload.enabled
            row.updated_at = now
        self._apply_key(row=row, payload=payload, provider=provider)
        await self.repository.save(row)
        await self.runtime.reload(self.repository)
        await self.cache.bump_version()
        return await self.get_settings()

    async def clear_key(self, purpose_value: str) -> AiSettingsReadSchema:
        purpose = self._purpose(purpose_value)
        row = await self.repository.get_by_purpose(purpose)
        if row is not None:
            row.api_key_ciphertext = None
            row.api_key_hint = None
            row.updated_at = datetime.now(UTC)
            await self.repository.save(row)
            await self.runtime.reload(self.repository)
            await self.cache.bump_version()
        return await self.get_settings()

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

    async def test(self, purpose_value: str) -> AiTestResultSchema:
        purpose = self._purpose(purpose_value)
        config = (
            self.runtime.chat_config
            if purpose == PURPOSE_CHAT
            else self.runtime.embedding_config
        )
        started = time.perf_counter()
        try:
            if purpose == PURPOSE_CHAT:
                if not self.runtime.text_generator.configured:
                    return AiTestResultSchema(
                        ok=False,
                        purpose=purpose,
                        provider=config.provider,
                        model=config.model,
                        latency_ms=0,
                        detail="No chat API key is configured.",
                    )
                await self.runtime.text_generator.complete_text(
                    "You are a connection test. Reply with OK.",
                    "OK",
                )
            else:
                if self.runtime.embedder.dimension <= 0:
                    return AiTestResultSchema(
                        ok=False,
                        purpose=purpose,
                        provider=config.provider,
                        model=config.model,
                        latency_ms=0,
                        detail="Embeddings are disabled.",
                    )
                await self.runtime.embedder.embed(["DendroMatrix connection test"])
        except (AiNotConfiguredError, AiProviderError, EmbeddingProviderError) as exc:
            return AiTestResultSchema(
                ok=False,
                purpose=purpose,
                provider=config.provider,
                model=config.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=str(exc),
            )
        return AiTestResultSchema(
            ok=True,
            purpose=purpose,
            provider=config.provider,
            model=config.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail="Connected.",
        )
