"""SQLAlchemy persistence for database-backed AI provider settings."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.ai_config_model import AiProviderConfigModel


class AiProviderConfigRepository:
    """One row per purpose; updates overwrite the same row."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_purpose(self, purpose: str) -> AiProviderConfigModel | None:
        statement = select(AiProviderConfigModel).where(AiProviderConfigModel.purpose == purpose)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> Sequence[AiProviderConfigModel]:
        statement = select(AiProviderConfigModel).order_by(AiProviderConfigModel.purpose)
        return list((await self.session.execute(statement)).scalars().all())

    async def save(self, config: AiProviderConfigModel) -> AiProviderConfigModel:
        self.session.add(config)
        await self.session.flush()
        return config
