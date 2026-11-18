"""Pure contract for a chat-completion provider used by summaries and RAG."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class AiCompletion(BaseModel):
    """One completion plus provider metadata."""

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    usage: dict[str, int]


class TextGeneratorProtocol(Protocol):
    """Minimal text-generation surface consumed by the knowledge slice."""

    @property
    def configured(self) -> bool: ...

    @property
    def model_name(self) -> str: ...

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion: ...

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion: ...
