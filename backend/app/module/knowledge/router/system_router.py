"""HTTP adapters for statistics and demo seeding."""

from fastapi import APIRouter, Depends

from app.module.knowledge.dependencies import get_demo_service, get_stats_service
from app.module.knowledge.schema.system_schema import DemoSeedSchema, StatsSchema
from app.module.knowledge.service.demo_service import DemoService
from app.module.knowledge.service.stats_service import StatsService

router = APIRouter(tags=["system"])


@router.get("/stats", response_model=StatsSchema, operation_id="getStats")
async def get_stats(
    stats_service: StatsService = Depends(get_stats_service),
) -> StatsSchema:
    return await stats_service.get_stats()


@router.post("/demo/seed", response_model=DemoSeedSchema, operation_id="seedDemo")
async def seed_demo(
    demo_service: DemoService = Depends(get_demo_service),
) -> DemoSeedSchema:
    """Populate an empty library with a small demo archive."""
    return await demo_service.seed()
