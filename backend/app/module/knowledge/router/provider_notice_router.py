"""Root-only HTTP surface for persistent provider-chain outage notices."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.dependency.auth import require_root
from app.module.auth.schema.auth_schema import UserSchema
from app.module.knowledge.dependencies import (
    get_embedding_backfill_status_service,
    get_provider_notice_service,
)
from app.module.knowledge.schema.provider_notice_schema import (
    ProviderErrorNoticeListSchema,
    ProviderErrorNoticeReadSchema,
)
from app.module.knowledge.schema.system_schema import EmbeddingBackfillStatusSchema
from app.module.knowledge.service.embedding_backfill_status import (
    EmbeddingBackfillStatusService,
)
from app.module.knowledge.service.provider_error_notice_service import (
    ProviderErrorNoticeService,
)

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_root)],
)


@router.get(
    "/provider-notices",
    response_model=ProviderErrorNoticeListSchema,
    operation_id="listProviderNotices",
)
async def list_provider_notices(
    status: Literal["open", "all"] = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
    service: ProviderErrorNoticeService = Depends(get_provider_notice_service),
) -> ProviderErrorNoticeListSchema:
    """Return provider-chain failures and the unresolved count."""
    return await service.list_notices(status=status, limit=limit)


@router.post(
    "/provider-notices/{notice_id}/resolve",
    response_model=ProviderErrorNoticeReadSchema,
    operation_id="resolveProviderNotice",
)
async def resolve_provider_notice(
    notice_id: int,
    user: UserSchema = Depends(require_root),
    service: ProviderErrorNoticeService = Depends(get_provider_notice_service),
) -> ProviderErrorNoticeReadSchema:
    """Mark one notice resolved on behalf of the acting root account."""
    return await service.resolve_notice(notice_id, user_id=user.user_id)


@router.post(
    "/provider-notices/resolve-all",
    response_model=ProviderErrorNoticeListSchema,
    operation_id="resolveAllProviderNotices",
)
async def resolve_all_provider_notices(
    user: UserSchema = Depends(require_root),
    service: ProviderErrorNoticeService = Depends(get_provider_notice_service),
) -> ProviderErrorNoticeListSchema:
    """Resolve every open notice and return the refreshed open list."""
    return await service.resolve_all(user_id=user.user_id)


@router.get(
    "/embedding-backfill",
    response_model=EmbeddingBackfillStatusSchema,
    operation_id="getEmbeddingBackfillStatus",
)
async def get_embedding_backfill_status(
    service: EmbeddingBackfillStatusService = Depends(get_embedding_backfill_status_service),
) -> EmbeddingBackfillStatusSchema:
    """Return how many passages still wait for an embedding, as counts only."""
    return await service.status()


@router.post(
    "/embedding-backfill/retry",
    response_model=EmbeddingBackfillStatusSchema,
    operation_id="retryEmbeddingBackfill",
)
async def retry_embedding_backfill(
    service: EmbeddingBackfillStatusService = Depends(get_embedding_backfill_status_service),
) -> EmbeddingBackfillStatusSchema:
    """Ask the worker to resume the backfill now (after a recharge, say)."""
    return await service.request_retry()


__all__ = ["router"]
