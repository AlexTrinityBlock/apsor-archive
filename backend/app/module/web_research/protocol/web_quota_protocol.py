"""Consumer-owned web usage allowance contract."""

from typing import Protocol


class WebQuotaProtocol(Protocol):
    """One account's web search and fetch allowance."""

    async def web_search_allowed(self) -> bool:
        """Return whether one web search provider call may run."""
        ...

    async def record_web_search(self) -> None:
        """Add one successful web search provider call."""
        ...

    async def web_fetch_allowed(self) -> bool:
        """Return whether one web fetch provider call may run."""
        ...

    async def record_web_fetch(self) -> None:
        """Add one successful web fetch provider call."""
        ...


__all__ = ["WebQuotaProtocol"]
