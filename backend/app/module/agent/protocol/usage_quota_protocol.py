"""Consumer-owned chat usage allowance contract."""

from typing import Protocol


class AgentQuotaProtocol(Protocol):
    """One account's chat allowance, resolved by the composition root."""

    async def chat_allowed(self) -> bool:
        """Return whether another chat step may start."""
        ...


__all__ = ["AgentQuotaProtocol"]
