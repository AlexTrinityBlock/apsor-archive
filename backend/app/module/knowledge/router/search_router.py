"""HTTP adapters for hybrid search."""

from fastapi import APIRouter, Depends, Query

from app.module.knowledge.dependencies import get_search_service
from app.module.knowledge.schema.search_schema import SearchResponseSchema
from app.module.knowledge.service.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponseSchema, operation_id="searchKnowledge")
async def search_knowledge(
    query: str = Query(min_length=1, max_length=200),
    result_number: int = Query(default=2, ge=1, le=20),
    include_history: bool = False,
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponseSchema:
    """Run BM25 and vector recall, then de-duplicate the merged candidates."""
    return await search_service.search(
        query,
        result_number=result_number,
        include_history=include_history,
    )
