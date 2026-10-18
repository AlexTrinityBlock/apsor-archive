"""HTTP adapter for the sparse timeline."""

from fastapi import APIRouter, Depends, Query

from app.module.knowledge.dependencies import get_timeline_service
from app.module.knowledge.schema.timeline_schema import TimelineResponseSchema
from app.module.knowledge.service.timeline_service import TimelineService

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("", response_model=TimelineResponseSchema, operation_id="readTimeline")
async def read_timeline(
    year: int = Query(ge=1900, le=2200),
    month: int = Query(ge=1, le=12),
    day: int = Query(ge=1, le=31),
    day_range: int = Query(default=1, ge=1, le=366),
    include_history: bool = False,
    timeline_service: TimelineService = Depends(get_timeline_service),
) -> TimelineResponseSchema:
    """Read a date range with up to five sampled events per source kind."""
    return await timeline_service.get_timeline(
        year=year,
        month=month,
        day=day,
        day_range=day_range,
        include_history=include_history,
    )
