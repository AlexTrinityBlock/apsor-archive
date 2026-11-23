"""Generic CRUD, validation, caching, and connection tests for providers.

One service instance drives all four capabilities.  The only capability-specific
branches are validation rules and the runtime slot used to report readiness.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import ROLE_USER, Database
from app.infrastructure.security.secret_cipher import SecretCipherError
from app.module.knowledge.domain.provider_config_domain import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CAPABILITY_WEB_SEARCH,
    PROVIDER_CAPABILITIES,
    PROVIDER_TABLE_SPECS,
    ProviderCapability,
    ProviderTableSpec,
    default_base_url_for,
)
from app.module.knowledge.exception.domain_error import (
    EmbeddingProviderError,
    InvalidProviderConfigError,
    KnowledgeError,
    ProviderNotFoundError,
)
from app.module.knowledge.model.chunk_model import ChunkModel
from app.module.knowledge.model.provider_config_model import ProviderConfigMixin
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
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
from app.module.knowledge.service.cache_keys import cache_key, user_version_scope
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

REGISTRY_CACHE_TTL_SECONDS = 30
PROVIDERS_CACHE_SCOPE = "providers"
REINDEX_BATCH_SIZE = 64

type ChunkRepositoryFactory = Callable[[AsyncSession, int], ChunkRepositoryProtocol]


@dataclass(frozen=True)
class _NormalizedProvider:
    """A validated payload after trimming and defaulting."""

    provider: str
    label: str
    model: str | None
    base_url: str | None
    dimension: int | None
    max_output_tokens: int | None


class ProviderConfigService:
    """Manage the global provider registry and fan embedding reindex out per owner.

    The service never returns or logs plaintext keys. Embedding reindex is the
    only operation that touches private chunk rows, and it does so exclusively
    inside each owner's scoped session. A model change rebuilds current and
    historical chunks because history remains searchable.
    """

    def __init__(
        self,
        *,
        user_id: int,
        database: Database,
        repository: ProviderConfigRepositoryProtocol,
        runtime: ProviderRuntimeProtocol,
        cipher: SecretCipherProtocol,
        defaults: ProviderDefaults,
        chunk_repository_factory: ChunkRepositoryFactory,
        cache: CacheProtocol,
        tester: ProviderTesterProtocol,
        registry_ttl_seconds: int = REGISTRY_CACHE_TTL_SECONDS,
    ) -> None:
        self.user_id = user_id
        self.database = database
        self.repository = repository
        self.runtime = runtime
        self.cipher = cipher
        self.defaults = defaults
        self.chunk_repository_factory = chunk_repository_factory
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
            active_rows = sorted(
                (row for row in rows if row.is_active),
                key=lambda row: (row.priority, row.id),
            )
            chain = [
                self._read_active(spec, row, primary=index == 0)
                for index, row in enumerate(active_rows)
            ]
            active = chain[0] if chain else self._read_virtual_active(spec)
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
                    chain=chain,
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
            max_output_tokens=getattr(row, "max_output_tokens", None),
            is_active=row.is_active,
            priority=row.priority,
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
        *,
        primary: bool,
    ) -> ProviderReadSchema:
        """Read one chain row, including any environment key fallback.

        The primary uses the aggregate runtime readiness so environment
        defaults and keyless providers stay consistent with the existing
        single-provider behaviour. A backup reports its own row-level
        credential state; the aggregate runtime only describes the head.
        """
        key_source: KeySource = "none"
        if row.api_key_ciphertext:
            key_source = "database"
        else:
            environment_key = self._environment_key(spec.capability, row.provider)
            if environment_key:
                key_source = "environment"
        hint = row.api_key_hint
        if hint is None and key_source == "environment":
            environment_key = self._environment_key(spec.capability, row.provider)
            if environment_key:
                hint = self.cipher.hint(environment_key)
        return ProviderReadSchema(
            id=row.id,
            capability=spec.capability,
            provider=row.provider,
            label=row.label or row.provider,
            model=row.model,
            base_url=row.base_url,
            dimension=row.dimension,
            max_output_tokens=getattr(row, "max_output_tokens", None),
            is_active=True,
            priority=row.priority,
            configured=(
                self._active_configured(spec)
                if primary
                else (
                    row.provider != "none"
                    and (
                        row.provider in spec.keyless_providers
                        or key_source != "none"
                    )
                )
            ),
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
            max_output_tokens=config.max_output_tokens,
            is_active=config.enabled,
            priority=0,
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
        """Report whether any owner's chunks use a model other than the active one.

        Current and historical chunks are both considered because a model change
        rebuilds every stored embedding, including rows reached by
        ``include_history`` searches.
        """
        if self.runtime.embedder.dimension <= 0:
            return False
        current_model = self.runtime.embedder.model_name
        try:
            owner_ids = await self._list_chunk_owner_ids()
        except Exception as exc:
            logger.warning(
                "Could not enumerate owners while checking embedding state (%s).",
                type(exc).__name__,
            )
            return True
        for owner_id in owner_ids:
            try:
                async with self.database.user_session(owner_id, ROLE_USER) as session:
                    repository = self.chunk_repository_factory(session, owner_id)
                    counts = await repository.embedding_model_counts(include_history=True)
                    total_chunks = await repository.count_chunks()
            except Exception as exc:
                logger.warning(
                    "Could not inspect embedding state for user %d (%s).",
                    owner_id,
                    type(exc).__name__,
                )
                return True
            if sum(counts.values()) < total_chunks:
                return True
            if any(model != current_model for model in counts):
                return True
        return False

    async def _list_chunk_owner_ids(self) -> list[int]:
        """Enumerate every owner with chunks without reading chunk content.

        Current and historical rows both count. The maintenance session is used
        only for this distinct owner-id query; every chunk read and write that
        follows runs inside that owner's ``user_session``.
        """
        async with self.database.maintenance_session() as session:
            statement = (
                select(ChunkModel.user_id)
                .distinct()
                .order_by(ChunkModel.user_id)
            )
            return [int(row[0]) for row in (await session.execute(statement)).all()]

    async def _bump_owner_index_version(self, owner_id: int) -> None:
        """Invalidate one owner's private search/timeline/stats cache namespace."""
        try:
            await self.cache.bump_version(user_version_scope(owner_id))
        except Exception:
            logger.warning(
                "Could not invalidate the private index cache for user %d.",
                owner_id,
            )

    async def _invalidate_owner_index_caches(self) -> None:
        """Invalidate every owner with chunks after an embedding change.

        Historical chunks can appear in searches with ``include_history``, so
        all chunk owners are invalidated, not only owners with current chunks.
        """
        try:
            owner_ids = await self._list_chunk_owner_ids()
        except Exception as exc:
            logger.warning(
                "Could not enumerate owners for embedding cache invalidation (%s).",
                type(exc).__name__,
            )
            await self._bump_owner_index_version(self.user_id)
            return
        for owner_id in owner_ids:
            await self._bump_owner_index_version(owner_id)

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
        # The mixin has no typed __init__; the concrete declarative class accepts
        # these mapped-column keywords. The cast only tells mypy about that shape.
        model_factory = cast(type[Any], spec.model)
        row_options: dict[str, Any] = {
            "provider": normalized.provider,
            "label": normalized.label,
            "model": normalized.model,
            "base_url": normalized.base_url,
            "dimension": normalized.dimension,
            "is_active": False,
            "priority": 0,
            "created_at": now,
            "updated_at": now,
        }
        if spec.capability == CAPABILITY_CHAT:
            # Only the chat table has the per-row output cap column.
            row_options["max_output_tokens"] = normalized.max_output_tokens
        row: ProviderConfigMixin = model_factory(**row_options)
        self._apply_key(
            row=row,
            payload=payload,
            keyless=normalized.provider in spec.keyless_providers,
        )
        # Save first to obtain the identity id. Inactive rows never participate
        # in the partial unique index, so the insert cannot conflict.
        await self.repository.save(row)
        if payload.activate:
            await self._append_to_chain(spec, row)
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
        if spec.capability == CAPABILITY_CHAT:
            # Only the chat table has the per-row output cap column.
            cast(Any, row).max_output_tokens = normalized.max_output_tokens
        row.updated_at = utcnow()
        self._apply_key(
            row=row,
            payload=payload,
            keyless=normalized.provider in spec.keyless_providers,
        )
        # Editing an inactive row only appends when activation is explicit.
        # Editing an active row keeps its position; activation is never a way to
        # reorder the chain.
        if payload.activate and not row.is_active:
            await self._append_to_chain(spec, row)
        else:
            if row.is_active:
                await self._validate_active_chain(spec)
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
        was_active = row.is_active
        remaining = [
            item
            for item in await self.repository.list_active_chain(spec)
            if item.id != row.id
        ]
        await self.repository.delete(row)
        if was_active:
            # Close the priority gap so the next row becomes the primary.
            await self.repository.replace_chain(spec, remaining)
        await self._after_write(spec)
        return await self.get_registry()

    async def activate(
        self,
        capability: str,
        provider_id: int,
        priority: int | None = None,
    ) -> ProviderRegistryReadSchema:
        """Add or move one row in the chain and renumber it deterministically."""
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        chain = [
            item
            for item in await self.repository.list_active_chain(spec)
            if item.id != row.id
        ]
        if priority is None:
            target = len(chain)
        else:
            if priority < 0 or priority > len(chain):
                raise InvalidProviderConfigError(
                    f"priority must be between 0 and {len(chain)}."
                )
            target = priority
        ordered = [*chain[:target], row, *chain[target:]]
        self._validate_embedding_chain(spec, ordered)
        await self.repository.replace_chain(spec, ordered)
        await self._after_write(spec)
        return await self.get_registry()

    async def deactivate_row(
        self,
        capability: str,
        provider_id: int,
    ) -> ProviderRegistryReadSchema:
        """Remove one row from the chain and close the resulting priority gap."""
        spec = self._spec(capability)
        row = await self.repository.get_by_id(spec, provider_id)
        if row is None:
            raise ProviderNotFoundError(provider_id)
        if row.is_active:
            remaining = [
                item
                for item in await self.repository.list_active_chain(spec)
                if item.id != row.id
            ]
            await self.repository.replace_chain(spec, remaining)
        await self._after_write(spec)
        return await self.get_registry()

    async def deactivate(self, capability: str) -> ProviderRegistryReadSchema:
        """Clear the whole active chain for one capability; runtime falls back."""
        spec = self._spec(capability)
        await self.repository.deactivate_all(spec)
        await self._after_write(spec)
        return await self.get_registry()

    async def _append_to_chain(
        self,
        spec: ProviderTableSpec,
        row: ProviderConfigMixin,
    ) -> None:
        """Append one row to the end of the active chain and renumber it."""
        chain = list(await self.repository.list_active_chain(spec))
        chain = [item for item in chain if item.id != row.id]
        chain.append(row)
        self._validate_embedding_chain(spec, chain)
        await self.repository.replace_chain(spec, chain)

    async def _validate_active_chain(self, spec: ProviderTableSpec) -> None:
        """Validate the current active chain after an in-place edit."""
        chain = list(await self.repository.list_active_chain(spec))
        self._validate_embedding_chain(spec, chain)

    @staticmethod
    def _validate_embedding_chain(
        spec: ProviderTableSpec,
        chain: list[ProviderConfigMixin],
    ) -> None:
        """Refuse an embedding chain whose backups use a different vector space.

        Different models (or dimensions of the same model) produce vectors that
        cannot be compared, so mixing them in one per-owner index would corrupt
        semantic recall. Multiple keys or providers are allowed as long as the
        model id and dimension are identical.
        """
        if spec.capability != CAPABILITY_EMBEDDING or len(chain) <= 1:
            return
        primary = chain[0]
        if primary.provider == "none":
            raise InvalidProviderConfigError(
                "The disabled embedding provider cannot be combined with other "
                "providers in one chain."
            )
        for row in chain[1:]:
            if row.provider == "none":
                raise InvalidProviderConfigError(
                    "The disabled embedding provider cannot be combined with other "
                    "providers in one chain."
                )
            if row.model != primary.model or row.dimension != primary.dimension:
                raise InvalidProviderConfigError(
                    "Embedding backups must use the primary's model and dimension "
                    f"(model={primary.model}, dimension={primary.dimension}). "
                    "Mixing embedding models or dimensions in one chain would "
                    "corrupt the per-owner vector index; change the primary and "
                    "re-index before adding this provider."
                )

    async def _after_write(self, spec: ProviderTableSpec) -> None:
        """Flush, refresh the runtime, then invalidate the scoped caches.

        A provider write invalidates the global registry cache. An embedding
        change also invalidates every owner's private index namespace because
        every owner's vectors were produced by the previous model. The
        maintenance scope is used only to enumerate owner ids.
        """
        await self.repository.flush()
        await self.runtime.reload(self.repository)
        await self.cache.bump_version(PROVIDERS_CACHE_SCOPE)
        if spec.capability == CAPABILITY_EMBEDDING:
            await self._invalidate_owner_index_caches()

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

        if spec.capability == CAPABILITY_CHAT:
            # A disabled chat row has no meaningful output cap; ignore a value
            # the dialog may still hold while the provider is "none".
            max_output_tokens = None if provider == "none" else payload.max_output_tokens
        else:
            if payload.max_output_tokens is not None:
                raise InvalidProviderConfigError(
                    "max_output_tokens is only supported by the chat capability."
                )
            max_output_tokens = None

        return _NormalizedProvider(
            provider=provider,
            label=label,
            model=model,
            base_url=base_url,
            dimension=dimension,
            max_output_tokens=max_output_tokens,
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
            return default_base_url_for(spec, provider)
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
        """Re-embed every owner's chunks, current and historical.

        The root request reads the global provider configuration and triggers the
        operation. Owner ids are enumerated through a maintenance query that
        selects only ``user_id``; chunk content is never read or written there.
        Each owner is processed in short, independently committed
        ``user_session`` batches, so one owner's failure or large corpus cannot
        hold a transaction across archives.

        A model change rebuilds historical chunks too because they remain
        reachable by ``include_history`` searches.

        This root-only maintenance path calls the embedder directly instead of
        going through ``IndexerService``. It is therefore exempt from account
        usage allowances and does not record embedding usage: an operator's
        provider migration must not be blocked by a per-account grant, and the
        reindex is not a user action.

        A failed owner is logged with its id and the exception type (never chunk
        or provider content), its stale search cache is still invalidated, and
        the remaining owners are processed. The response therefore reports every
        chunk that was committed, including batches completed before a failure.
        """
        await self.runtime.reload(self.repository)
        spec = PROVIDER_TABLE_SPECS[CAPABILITY_EMBEDDING]
        active_row = await self.repository.get_active(spec)
        if active_row is not None:
            active_config = self._config_from_row(spec, active_row)
            if not active_config.enabled or active_config.provider == "none":
                raise InvalidProviderConfigError("Embeddings are disabled.")
        embedder = self.runtime.embedder
        if embedder.dimension <= 0:
            raise InvalidProviderConfigError("Embeddings are disabled.")
        try:
            owner_ids = await self._list_chunk_owner_ids()
        except Exception as exc:
            logger.error(
                "Could not enumerate owners for embedding reindex (%s).",
                type(exc).__name__,
            )
            raise KnowledgeError("Embedding reindex could not start.") from exc

        started = time.perf_counter()
        reindexed = 0
        failed_owners = 0
        for owner_id in owner_ids:
            updated, failed = await self._reindex_owner_embeddings(
                owner_id,
                embedder,
                batch_size=REINDEX_BATCH_SIZE,
            )
            reindexed += updated
            # Even a failed attempt must drop cached results computed with the
            # previous model; the next search then runs against the new state.
            await self._bump_owner_index_version(owner_id)
            if failed:
                failed_owners += 1
            else:
                logger.info(
                    "Reindexed %d embedding(s) for user %d.",
                    updated,
                    owner_id,
                )
        if failed_owners:
            logger.warning(
                "Embedding reindex finished with %d failed owner(s); %d chunk(s) updated.",
                failed_owners,
                reindexed,
            )
        return EmbeddingReindexSchema(
            reindexed=reindexed,
            model=embedder.model_name,
            dimension=embedder.dimension,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _reindex_owner_embeddings(
        self,
        owner_id: int,
        embedder: EmbedderProtocol,
        *,
        batch_size: int,
    ) -> tuple[int, bool]:
        """Re-embed one owner in short, independently committed batches.

        Every chunk owned by the account is included, current and historical.
        """
        after_id = 0
        updated = 0
        while True:
            try:
                async with self.database.user_session(owner_id, ROLE_USER) as session:
                    repository = self.chunk_repository_factory(session, owner_id)
                    chunks = await repository.list_chunks_after(
                        after_id=after_id,
                        limit=batch_size,
                    )
                    if not chunks:
                        return updated, False
                    vectors = await embedder.embed([chunk.content for chunk in chunks])
                    if len(vectors) != len(chunks):
                        raise EmbeddingProviderError(
                            f"The provider returned {len(vectors)} vectors for "
                            f"{len(chunks)} chunks."
                        )
                    for chunk, vector in zip(chunks, vectors, strict=True):
                        await repository.update_embedding(
                            chunk.id,
                            vector,
                            embedder.model_name,
                        )
                    after_id = chunks[-1].id
            except Exception as exc:
                logger.error(
                    "Embedding reindex failed for user %d after %d chunk(s) (%s).",
                    owner_id,
                    updated,
                    type(exc).__name__,
                )
                return updated, True
            updated += len(chunks)

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
        if not row.api_key_ciphertext:
            # Environment enrichment applies only to a row with no stored
            # ciphertext. A failed decryption stays keyless so a corrupted key is
            # reported instead of silently borrowing another secret.
            key = self._environment_key(spec.capability, row.provider)
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
            row_id=row.id,
            # Effort is supplied by the account assignment; the shared endpoint
            # row never stores it.
            reasoning_effort=None,
            max_output_tokens=getattr(row, "max_output_tokens", None),
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

    def _environment_key(
        self,
        capability: ProviderCapability,
        provider: str,
    ) -> str | None:
        if capability == CAPABILITY_CHAT:
            # Provider-aware, exactly like ``AiRuntime``: an Anthropic row may
            # receive only the Anthropic deployment key, never the DeepSeek one.
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


__all__ = ["ProviderConfigService"]
