"""Consumer-owned chat usage allowance contract for knowledge services."""

from collections.abc import Mapping
from typing import Protocol


class ChatUsageQuotaProtocol(Protocol):
    """One account's chat allowance and background-usage recorder."""

    async def chat_allowed(self) -> bool:
        """Return whether another chat provider call may start."""
        ...

    async def record_chat_usage(self, usage: Mapping[str, int]) -> None:
        """Record one successful background provider call."""
        ...


__all__ = ["ChatUsageQuotaProtocol"]
