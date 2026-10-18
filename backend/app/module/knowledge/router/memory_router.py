"""HTTP adapters for the memory timeline and summaries."""

from fastapi import APIRouter, Depends, Query, status

from app.module.knowledge.dependencies import get_memory_service, get_summary_service
from app.module.knowledge.schema.memory_schema import (
    MemoryCreateSchema,
    MemoryReadSchema,
    MemorySaveSchema,
    MemorySchema,
    SummaryCreateSchema,
    SummarySchema,
)
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.summary_service import SummaryService
from app.shared.types.list_response import ListResponseSchema

router = APIRouter(tags=["memories"])


@router.post(
    "/memories",
    response_model=MemorySaveSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="saveMemory",
)
async def save_memory(
    payload: MemoryCreateSchema,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemorySaveSchema:
    """Create a memory and deprecate the memories it replaces."""
    return await memory_service.save_memory(
        content=payload.content,
        supersedes=payload.supersedes,
        occurred_at=payload.occurred_at,
        source=payload.source,
    )


@router.get(
    "/memories",
    response_model=ListResponseSchema[MemorySchema],
    operation_id="listMemories",
)
async def list_memories(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    memory_service: MemoryService = Depends(get_memory_service),
) -> ListResponseSchema[MemorySchema]:
    resources = await memory_service.list_memories(limit=limit, offset=offset)
    total = await memory_service.count_all()
    return ListResponseSchema[MemorySchema](
        total_results=total,
        start_index=offset + 1,
        items_per_page=limit,
        resources=resources,
    )


@router.get(
    "/memories/{memory_id}",
    response_model=MemoryReadSchema,
    operation_id="readMemory",
)
async def read_memory(
    memory_id: int,
    memory_range: int = Query(default=0, ge=0, le=10),
    trace_history: bool = True,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryReadSchema:
    """Read a memory, its neighbors, and its supersession chain."""
    return await memory_service.read_memory(
        memory_id,
        memory_range=memory_range,
        trace_history=trace_history,
    )


@router.post(
    "/summaries",
    response_model=SummarySchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSummary",
)
async def create_summary(
    payload: SummaryCreateSchema,
    summary_service: SummaryService = Depends(get_summary_service),
) -> SummarySchema:
    """Summarize explicit memories or the unsummarized memories in a period."""
    return await summary_service.create_summary(
        period_start=payload.period_start,
        period_end=payload.period_end,
        memory_ids=payload.memory_ids,
        force=payload.force,
    )


@router.get(
    "/summaries",
    response_model=ListResponseSchema[SummarySchema],
    operation_id="listSummaries",
)
async def list_summaries(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    summary_service: SummaryService = Depends(get_summary_service),
) -> ListResponseSchema[SummarySchema]:
    resources = await summary_service.list_summaries(limit=limit, offset=offset)
    total = await summary_service.count_summaries()
    return ListResponseSchema[SummarySchema](
        total_results=total,
        start_index=offset + 1,
        items_per_page=limit,
        resources=resources,
    )


@router.get(
    "/summaries/{summary_id}",
    response_model=SummarySchema,
    operation_id="getSummary",
)
async def get_summary(
    summary_id: int,
    summary_service: SummaryService = Depends(get_summary_service),
) -> SummarySchema:
    return await summary_service.get_summary(summary_id)
