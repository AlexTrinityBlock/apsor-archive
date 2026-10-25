"""Pure contract for the cache used by read-heavy endpoints."""

from typing import Protocol

type JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class CacheProtocol(Protocol):
    """Read-through cache with one monotonic version per logical scope.

    ``scope`` defaults to ``"index"`` so every pre-existing caller keeps the old
    behaviour.  Provider writes use ``"providers"`` and prompt writes use
    ``"prompts"`` so invalidating one registry never flushes the whole archive.
    """

    async def get_json(self, key: str) -> JsonValue | None: ...

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None: ...

    async def get_version(self, scope: str = "index") -> int: ...

    async def bump_version(self, scope: str = "index") -> int: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...
