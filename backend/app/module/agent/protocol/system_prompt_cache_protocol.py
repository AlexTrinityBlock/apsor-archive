"""Consumer-owned cache contract for the system-prompt slice.

The agent slice must not import another slice's cache protocol. The application
cache structurally satisfies this minimal contract.
"""

from typing import Protocol

type JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class SystemPromptCacheProtocol(Protocol):
    """Read-through cache with a scoped monotonic version."""

    async def get_json(self, key: str) -> JsonValue | None: ...

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None: ...

    async def get_version(self, scope: str = "index") -> int: ...

    async def bump_version(self, scope: str = "index") -> int: ...


__all__ = ["JsonValue", "SystemPromptCacheProtocol"]
