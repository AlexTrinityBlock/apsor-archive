"""In-memory cache used as a fallback when Valkey is unavailable."""

import asyncio
import time

from app.module.knowledge.protocol.cache_protocol import JsonValue


class MemoryCache:
    """A tiny TTL cache scoped to one process."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, JsonValue]] = {}
        self._version = 1
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

    async def get_version(self) -> int:
        return self._version

    async def bump_version(self) -> int:
        async with self._lock:
            self._version += 1
            return self._version

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._values.clear()
