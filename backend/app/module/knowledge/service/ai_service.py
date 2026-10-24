"""AI configuration status."""

from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.schema.ai_schema import AiStatusSchema


class AiService:
    """Report the active chat and vector configuration."""

    def __init__(
        self,
        *,
        text_generator: TextGeneratorProtocol,
        embedding_provider: str,
        embedding_model: str,
        vector_enabled: bool,
    ) -> None:
        self.text_generator = text_generator
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.vector_enabled = vector_enabled

    def status(self) -> AiStatusSchema:
        return AiStatusSchema(
            configured=self.text_generator.configured,
            model=self.text_generator.model_name,
            provider="deepseek" if self.text_generator.configured else "none",
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            vector_enabled=self.vector_enabled,
        )
