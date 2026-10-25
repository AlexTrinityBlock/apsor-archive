"""AI configuration status."""

from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.schema.ai_schema import AiStatusSchema


class AiService:
    """Report the active chat and vector configuration."""

    def __init__(
        self,
        *,
        text_generator: TextGeneratorProtocol,
        chat_provider: str,
        chat_model: str | None,
        embedding_provider: str,
        embedding_model: str,
        vector_enabled: bool,
    ) -> None:
        self.text_generator = text_generator
        self.chat_provider = chat_provider
        self.chat_model = chat_model
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.vector_enabled = vector_enabled

    def status(self) -> AiStatusSchema:
        # 這裡必須回報實際的 chat provider，而不是假設 DeepSeek；openai-compatible
        # 也是合法的 chat provider，診斷頁不能把它顯示成 deepseek。
        configured = self.text_generator.configured
        return AiStatusSchema(
            configured=configured,
            model=self.chat_model or self.text_generator.model_name,
            provider=self.chat_provider if configured else "none",
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            vector_enabled=self.vector_enabled,
        )
