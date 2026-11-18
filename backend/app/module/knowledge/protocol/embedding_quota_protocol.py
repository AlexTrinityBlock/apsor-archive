"""Consumer-owned embedding usage allowance contract."""

from typing import Protocol


class EmbeddingQuotaProtocol(Protocol):
    """One account's embedding allowance, resolved by the composition root."""

    async def embedding_allowed(self, units: int) -> bool:
        """Return whether one batch of ``units`` estimated tokens fits."""
        ...

    async def record_embedding(self, units: int) -> None:
        """Add a successfully embedded batch to the lifetime counter."""
        ...


__all__ = ["EmbeddingQuotaProtocol"]
