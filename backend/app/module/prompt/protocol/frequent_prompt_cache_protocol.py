"""Consumer-owned cache contract for the frequent-prompt slice.

The prompt slice must not import another slice's protocol.  The application
cache structurally satisfies this minimal contract.
"""

from typing import Protocol

type JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class FrequentPromptCacheProtocol(Protocol):
    """Read-through cache with a scoped monotonic version."""

    async def get_json(self, key: str) -> JsonValue | None: ...

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None: ...

    async def get_version(self, scope: str = "index") -> int: ...

    async def bump_version(self, scope: str = "index") -> int: ...


__all__ = ["FrequentPromptCacheProtocol", "JsonValue"]
