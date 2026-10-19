"""SQLAlchemy persistence for the singleton ingestion runtime configuration."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.module.knowledge.model.ingest_config_model import IngestConfigModel

SINGLETON_ID = 1


class IngestConfigRepository:
    """One row with ``id=1``; the injected session owns its transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_singleton(self) -> IngestConfigModel | None:
        return await self.session.get(IngestConfigModel, SINGLETON_ID)

    async def save(self, config: IngestConfigModel) -> IngestConfigModel:
        self.session.add(config)
        await self.session.flush()
        return config


__all__ = ["SINGLETON_ID", "IngestConfigRepository"]
