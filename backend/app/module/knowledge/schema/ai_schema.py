"""Schemas for AI configuration status."""

from pydantic import BaseModel, ConfigDict


class AiStatusSchema(BaseModel):
    """Configuration state for the AI and vector paths."""

    model_config = ConfigDict(frozen=True)

    configured: bool
    model: str
    provider: str
    embedding_provider: str
    embedding_model: str
    vector_enabled: bool
