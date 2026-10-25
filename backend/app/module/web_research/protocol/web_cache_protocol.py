"""Consumer-owned subset of the cache used by the web research slice.

``get_version(scope)`` is the important part: provider writes bump the
``providers`` scope, so every cached search/fetch entry becomes unreachable
without scanning or deleting keys. The real cache lives behind
``app.state.cache`` and is adapted structurally at the composition root.
"""

from typing import Protocol

type JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class WebCacheProtocol(Protocol):
    async def get_json(self, key: str) -> JsonValue | None: ...

    async def set_json(self, key: str, value: JsonValue, ttl_seconds: int) -> None: ...

    async def get_version(self, scope: str = "index") -> int: ...
