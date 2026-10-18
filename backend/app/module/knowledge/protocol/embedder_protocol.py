"""Pure contract for an embedding provider."""

from typing import Protocol


class EmbedderProtocol(Protocol):
    """Turn text batches into L2-normalized vectors."""

    dimension: int
    model_name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
