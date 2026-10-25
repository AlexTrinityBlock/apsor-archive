"""Capability literals and the per-table specification used by the registry.

Every provider table is addressed through a :class:`ProviderTableSpec`, which
lets one repository, one service, and one runtime snapshot treat the four
physical tables uniformly without copy-pasting CRUD code.
"""

from dataclasses import dataclass
from typing import Literal

from app.module.knowledge.model.provider_config_model import (
    ChatProviderConfigModel,
    EmbeddingProviderConfigModel,
    ProviderConfigMixin,
    WebFetchProviderConfigModel,
    WebSearchProviderConfigModel,
)

ProviderCapability = Literal["chat", "embedding", "web_search", "web_fetch"]

CAPABILITY_CHAT: ProviderCapability = "chat"
CAPABILITY_EMBEDDING: ProviderCapability = "embedding"
CAPABILITY_WEB_SEARCH: ProviderCapability = "web_search"
CAPABILITY_WEB_FETCH: ProviderCapability = "web_fetch"

PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CAPABILITY_WEB_SEARCH,
    CAPABILITY_WEB_FETCH,
)

WEB_CAPABILITIES: frozenset[ProviderCapability] = frozenset(
    {CAPABILITY_WEB_SEARCH, CAPABILITY_WEB_FETCH}
)


@dataclass(frozen=True)
class ProviderTableSpec:
    """Everything the generic CRUD layer needs to know about one table."""

    capability: ProviderCapability
    title: str
    description: str
    model: type[ProviderConfigMixin]
    allowed_providers: frozenset[str]
    keyless_providers: frozenset[str]
    default_base_url: str | None
    supports_model: bool
    supports_dimension: bool


CHAT_TABLE_SPEC = ProviderTableSpec(
    capability=CAPABILITY_CHAT,
    title="Chat",
    description=(
        "Large-language-model providers used for summaries, extraction, and agent answers."
    ),
    model=ChatProviderConfigModel,
    allowed_providers=frozenset({"deepseek", "openai-compatible", "none"}),
    keyless_providers=frozenset({"none"}),
    default_base_url="https://api.deepseek.com",
    supports_model=True,
    supports_dimension=False,
)

EMBEDDING_TABLE_SPEC = ProviderTableSpec(
    capability=CAPABILITY_EMBEDDING,
    title="Embedding",
    description="Vector embedding providers used for semantic recall and re-indexing.",
    model=EmbeddingProviderConfigModel,
    allowed_providers=frozenset({"hashing", "openai", "openai-compatible", "none"}),
    keyless_providers=frozenset({"hashing", "none"}),
    default_base_url="https://api.openai.com/v1",
    supports_model=True,
    supports_dimension=True,
)

WEB_SEARCH_TABLE_SPEC = ProviderTableSpec(
    capability=CAPABILITY_WEB_SEARCH,
    title="Web search",
    description="Read-only search providers used by the agent's web_search tool.",
    model=WebSearchProviderConfigModel,
    allowed_providers=frozenset({"tavily", "none"}),
    keyless_providers=frozenset({"none"}),
    default_base_url="https://api.tavily.com",
    supports_model=False,
    supports_dimension=False,
)

WEB_FETCH_TABLE_SPEC = ProviderTableSpec(
    capability=CAPABILITY_WEB_FETCH,
    title="Web fetch",
    description="Read-only page-fetch providers used by the agent's web_fetch tool.",
    model=WebFetchProviderConfigModel,
    allowed_providers=frozenset({"tavily", "none"}),
    keyless_providers=frozenset({"none"}),
    default_base_url="https://api.tavily.com",
    supports_model=False,
    supports_dimension=False,
)

PROVIDER_TABLE_SPECS: dict[ProviderCapability, ProviderTableSpec] = {
    CAPABILITY_CHAT: CHAT_TABLE_SPEC,
    CAPABILITY_EMBEDDING: EMBEDDING_TABLE_SPEC,
    CAPABILITY_WEB_SEARCH: WEB_SEARCH_TABLE_SPEC,
    CAPABILITY_WEB_FETCH: WEB_FETCH_TABLE_SPEC,
}


__all__ = [
    "CAPABILITY_CHAT",
    "CAPABILITY_EMBEDDING",
    "CAPABILITY_WEB_FETCH",
    "CAPABILITY_WEB_SEARCH",
    "PROVIDER_CAPABILITIES",
    "PROVIDER_TABLE_SPECS",
    "WEB_CAPABILITIES",
    "ProviderCapability",
    "ProviderTableSpec",
]
