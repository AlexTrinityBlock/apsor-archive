"""Dashboard statistics with cache."""

from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.stats_repository_protocol import StatsRepositoryProtocol
from app.module.knowledge.schema.system_schema import StatsSchema
from app.module.knowledge.service.cache_keys import cache_key


class StatsService:
    """Read aggregate counts and cache them under the index version."""

    def __init__(
        self,
        *,
        stats_repository: StatsRepositoryProtocol,
        cache: CacheProtocol,
        cache_ttl_seconds: int,
    ) -> None:
        self.stats_repository = stats_repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def get_stats(self) -> StatsSchema:
        version = await self.cache.get_version()
        key = cache_key(version, "stats")
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return StatsSchema.model_validate(cached)

        snapshot = await self.stats_repository.snapshot()
        response = StatsSchema(
            file_count=snapshot.file_count,
            chunk_count=snapshot.chunk_count,
            memory_count=snapshot.memory_count,
            active_memory_count=snapshot.active_memory_count,
            summary_count=snapshot.summary_count,
            storage_bytes=snapshot.storage_bytes,
            oldest_memory_time=snapshot.oldest_memory_time,
            newest_memory_time=snapshot.newest_memory_time,
        )
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response
