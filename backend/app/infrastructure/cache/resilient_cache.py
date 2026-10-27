"""Cache wrapper that degrades to memory instead of failing a request."""

import logging

from app.infrastructure.cache.memory_cache import MemoryCache
from app.module.knowledge.protocol.cache_protocol import CacheProtocol, JsonValue

logger = logging.getLogger(__name__)


class ResilientCache:
    """Use Valkey first and fall back to a process-local cache on failure."""

    def __init__(self, primary: CacheProtocol | None) -> None:
        self._primary = primary
        self._fallback = MemoryCache()
        self._warned = False

    def _warn(self, operation: str, exc: Exception) -> None:
        if not self._warned:
            logger.warning("Cache %s failed; using memory fallback: %s", operation, exc)
            self._warned = True

    async def get_json(self, key: str) -> JsonValue | None:
        if self._primary is not None:
            try:
                value = await self._primary.get_json(key)
                if value is not None:
                    return value
            except Exception as exc:  # Cache failures must not break reads.
                self._warn("get_json", exc)
        return await self._fallback.get_json(key)

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None:
        if self._primary is not None:
            try:
                await self._primary.set_json(key, value, ttl_seconds)
            except Exception as exc:  # Cache failures must not break writes.
                self._warn("set_json", exc)
        await self._fallback.set_json(key, value, ttl_seconds)

    async def get_version(self, scope: str = "index") -> int:
        if self._primary is not None:
            try:
                return await self._primary.get_version(scope)
            except Exception as exc:
                self._warn("get_version", exc)
        return await self._fallback.get_version(scope)

    async def bump_version(self, scope: str = "index") -> int:
        # Bump both layers; otherwise a stale scope version is read once Valkey recovers.
        version = await self._fallback.bump_version(scope)
        if self._primary is not None:
            try:
                return await self._primary.bump_version(scope)
            except Exception as exc:
                self._warn("bump_version", exc)
        return version

    async def ping(self) -> bool:
        if self._primary is not None:
            try:
                return await self._primary.ping()
            except Exception as exc:
                self._warn("ping", exc)
        return True

    async def close(self) -> None:
        await self._fallback.close()
        if self._primary is not None:
            try:
                await self._primary.close()
            except Exception as exc:
                logger.warning("Cache close failed: %s", exc)


def build_cache(url: str) -> ResilientCache:
    """Build a cache from a URL, or memory-only when the URL is empty."""
    from app.infrastructure.cache.valkey_cache import ValkeyCache

    normalized = url.strip().lower()
    if not normalized or normalized in {"memory://", "none"}:
        return ResilientCache(primary=None)
    return ResilientCache(primary=ValkeyCache(url))
