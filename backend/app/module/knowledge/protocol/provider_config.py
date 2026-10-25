"""Provider configuration value objects shared by the service and runtime."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.module.knowledge.domain.provider_config_domain import ProviderCapability

ProviderSource = Literal["database", "environment", "default"]


class ProviderConfig(BaseModel):
    """Resolved provider settings; ``api_key`` is plaintext only in memory.

    This object is internal to the server.  It must never be returned from a
    router because it carries the decrypted API key.
    """

    model_config = ConfigDict(frozen=True)

    capability: ProviderCapability
    provider: str
    label: str
    model: str | None
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
    web_search_provider: str = "none"
    web_search_base_url: str = "https://api.tavily.com"
    web_search_api_key: str | None = None
    web_fetch_provider: str = "none"
    web_fetch_base_url: str = "https://api.tavily.com"
    web_fetch_api_key: str | None = None


@dataclass(frozen=True)
class ProviderSnapshot:
    """The four resolved capability slots loaded by ``AiRuntime.reload``."""

    chat: ProviderConfig
    embedding: ProviderConfig
    web_search: ProviderConfig
    web_fetch: ProviderConfig


__all__ = [
    "ProviderCapability",
    "ProviderConfig",
    "ProviderDefaults",
    "ProviderSnapshot",
    "ProviderSource",
]
