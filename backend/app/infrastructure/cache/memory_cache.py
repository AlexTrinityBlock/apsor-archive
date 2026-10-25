"""In-memory cache used as a fallback when Valkey is unavailable."""

import asyncio
import time

from app.module.knowledge.protocol.cache_protocol import JsonValue

DEFAULT_INDEX_SCOPE = "index"


class MemoryCache:
    """A tiny TTL cache scoped to one process."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, JsonValue]] = {}
        # 每個 scope 一個 monotonic version（index、providers、prompts…）。
        self._versions: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def get_json(self, key: str) -> JsonValue | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._values.pop(key, None)
            return None
        return value

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None:
        self._values[key] = (time.monotonic() + ttl_seconds, value)

    async def get_version(self, scope: str = DEFAULT_INDEX_SCOPE) -> int:
        return self._versions.get(scope, 1)

    async def bump_version(self, scope: str = DEFAULT_INDEX_SCOPE) -> int:
        async with self._lock:
            version = self._versions.get(scope, 1) + 1
            self._versions[scope] = version
            return version

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._values.clear()
