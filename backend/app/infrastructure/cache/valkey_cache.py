"""Valkey/Redis cache implementation with JSON values."""

import json

from redis.asyncio import Redis

from app.module.knowledge.protocol.cache_protocol import JsonValue

VERSION_KEY = "dendro:index:version"


class ValkeyCache:
    """A Valkey-backed cache using the Redis protocol."""

    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url, decode_responses=True)

    async def get_json(self, key: str) -> JsonValue | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None:
        await self._client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)

    async def get_version(self) -> int:
        raw = await self._client.get(VERSION_KEY)
        if raw is None:
            await self._client.set(VERSION_KEY, 1)
            return 1
        return int(raw)

    async def bump_version(self) -> int:
        return int(await self._client.incr(VERSION_KEY))

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
