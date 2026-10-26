"""Schemas that are not part of the provider registry itself."""

from pydantic import BaseModel, ConfigDict


class EmbeddingReindexSchema(BaseModel):
    """The result of re-embedding the current and historical chunk corpus."""

    model_config = ConfigDict(frozen=True)

    reindexed: int
    model: str
    dimension: int
    elapsed_ms: int


__all__ = ["EmbeddingReindexSchema"]
