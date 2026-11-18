"""Consumer-owned embedding usage allowance contract."""

from typing import Protocol


class EmbeddingQuotaProtocol(Protocol):
    """One account's embedding allowance, resolved by the composition root."""

    async def embedding_allowed(self, characters: int) -> bool:
        """Return whether one batch of ``characters`` fits."""
        ...

    async def record_embedding(self, characters: int) -> None:
        """Add a successfully embedded batch's character count."""
        ...


__all__ = ["EmbeddingQuotaProtocol"]
