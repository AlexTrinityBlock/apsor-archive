"""HTTP adapters for statistics."""

from fastapi import APIRouter, Depends

from app.module.knowledge.dependencies import get_stats_service
from app.module.knowledge.schema.system_schema import StatsSchema
from app.module.knowledge.service.stats_service import StatsService

router = APIRouter(tags=["system"])


@router.get("/stats", response_model=StatsSchema, operation_id="getStats")
async def get_stats(
    stats_service: StatsService = Depends(get_stats_service),
) -> StatsSchema:
    return await stats_service.get_stats()
