"""Persistence contract for AI provider configuration."""

from collections.abc import Sequence
from typing import Protocol

from app.module.knowledge.model.ai_config_model import AiProviderConfigModel


class AiConfigRepositoryProtocol(Protocol):
    async def get_by_purpose(self, purpose: str) -> AiProviderConfigModel | None: ...

    async def list_all(self) -> Sequence[AiProviderConfigModel]: ...

    async def save(self, config: AiProviderConfigModel) -> AiProviderConfigModel: ...
