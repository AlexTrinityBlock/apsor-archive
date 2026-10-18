"""Pure contract for turning provider configuration into clients."""

from typing import Protocol

from app.module.knowledge.protocol.embedder_protocol import EmbedderProtocol
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol


class ProviderBuilderProtocol(Protocol):
    """Build infrastructure clients from resolved configuration."""

    def build_text_generator(self, config: ProviderConfig) -> TextGeneratorProtocol: ...

    def build_embedder(self, config: ProviderConfig) -> EmbedderProtocol: ...
