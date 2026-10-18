"""Provider configuration value objects shared by the service and runtime."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ProviderSource = Literal["database", "environment", "default"]

CHAT_PROVIDERS = frozenset({"deepseek", "openai-compatible", "none"})
EMBEDDING_PROVIDERS = frozenset({"hashing", "openai", "openai-compatible", "none"})
KEYLESS_PROVIDERS = frozenset({"hashing", "none"})


class ProviderConfig(BaseModel):
    """Resolved provider settings; ``api_key`` is plaintext only in memory."""

    model_config = ConfigDict(frozen=True)

    purpose: Literal["chat", "embedding"]
    provider: str
    model: str
    base_url: str | None
    api_key: str | None
    dimension: int | None
    enabled: bool
    source: ProviderSource


class ProviderDefaults(BaseModel):
    """Environment/bootstrap values used when no database row exists."""

    model_config = ConfigDict(frozen=True)

    chat_provider: str
    chat_model: str
    chat_base_url: str
    chat_api_key: str | None
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str | None
    embedding_api_key: str | None
    embedding_dimension: int
