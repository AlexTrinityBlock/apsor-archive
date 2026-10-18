"""Pure contract for the cache used by read-heavy endpoints."""

from typing import Protocol

type JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class CacheProtocol(Protocol):
    """Read-through cache with a monotonic index version."""

    async def get_json(self, key: str) -> JsonValue | None: ...

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None: ...

    async def get_version(self) -> int: ...

    async def bump_version(self) -> int: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...
