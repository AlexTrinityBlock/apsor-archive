"""Schemas for AI configuration status."""

from pydantic import BaseModel, ConfigDict


class AiStatusSchema(BaseModel):
    """Configuration state for the AI, vector, and web paths."""

    model_config = ConfigDict(frozen=True)

    configured: bool
    model: str
    provider: str
    embedding_provider: str
    embedding_model: str
    vector_enabled: bool
    web_search_provider: str = "none"
    web_search_configured: bool = False
    web_fetch_provider: str = "none"
    web_fetch_configured: bool = False
