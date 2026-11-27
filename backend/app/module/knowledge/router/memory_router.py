"""HTTP adapters for the memory timeline and summaries."""

from fastapi import APIRouter, Depends, Query, status

from app.module.knowledge.dependencies import (
    get_memory_service,
    get_related_memory_service,
    get_summary_service,
)
from app.module.knowledge.schema.memory_schema import (
    MemoryCreateSchema,
    MemoryDeprecateSchema,
    MemoryReadSchema,
    MemorySaveSchema,
    MemorySchema,
    MemoryUpdateSchema,
    RelatedMemoriesSchema,
    SummaryCreateSchema,
    SummarySchema,
)
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.related_memory_service import RelatedMemoryService
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


@router.patch(
    "/memories/{memory_id}",
    response_model=MemorySchema,
    operation_id="updateMemory",
)
async def update_memory(
    memory_id: int,
    payload: MemoryUpdateSchema,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemorySchema:
    """Edit one memory's text and republish its search chunk."""
    return await memory_service.update_memory(memory_id, content=payload.content)


@router.post(
    "/memories/{memory_id}/deprecate",
    response_model=MemorySchema,
    operation_id="deprecateMemory",
)
async def deprecate_memory(
    memory_id: int,
    payload: MemoryDeprecateSchema | None = None,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemorySchema:
    """Retire one memory without recording a replacement."""
    return await memory_service.deprecate_memory(
        memory_id,
        reason=payload.reason if payload is not None else None,
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
    "/memories/related/files/{file_id}",
    response_model=RelatedMemoriesSchema,
    operation_id="listFileRelatedMemories",
)
async def list_file_related_memories(
    file_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    related_service: RelatedMemoryService = Depends(get_related_memory_service),
) -> RelatedMemoriesSchema:
    """Rank memories related to one file by stored similarity and shared keywords."""
    return await related_service.related_to_file(file_id, limit=limit)


@router.get(
    "/memories/{memory_id}/related",
    response_model=RelatedMemoriesSchema,
    operation_id="listRelatedMemories",
)
async def list_related_memories(
    memory_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    include_deprecated: bool = False,
    related_service: RelatedMemoryService = Depends(get_related_memory_service),
) -> RelatedMemoriesSchema:
    """Rank memories related to one memory, excluding its supersession chain."""
    return await related_service.related_to_memory(
        memory_id,
        limit=limit,
        include_deprecated=include_deprecated,
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
