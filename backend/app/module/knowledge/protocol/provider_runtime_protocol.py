"""Consumer-owned runtime contract used by the provider settings service.

The service must not import the concrete ``AiRuntime`` from infrastructure.  The
runtime object satisfies this protocol structurally; the composition root still
decides which implementation is injected.
"""

from typing import Protocol

from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_builder_protocol import WebClientProtocol
from app.module.knowledge.protocol.provider_config import ProviderConfig, ProviderDefaults
from app.module.knowledge.protocol.provider_config_repository_protocol import (
    ProviderConfigRepositoryProtocol,
)
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol


class ProviderRuntimeProtocol(Protocol):
    """The live provider snapshot plus a reload hook."""

    defaults: ProviderDefaults
    chat_config: ProviderConfig
    embedding_config: ProviderConfig
    web_search_config: ProviderConfig
    web_fetch_config: ProviderConfig
    text_generator: TextGeneratorProtocol
    embedder: EmbedderProtocol
    web_search_client: WebClientProtocol
    web_fetch_client: WebClientProtocol

    @property
    def vector_enabled(self) -> bool: ...

    async def reload(self, repository: ProviderConfigRepositoryProtocol) -> None: ...


__all__ = ["ProviderRuntimeProtocol"]
