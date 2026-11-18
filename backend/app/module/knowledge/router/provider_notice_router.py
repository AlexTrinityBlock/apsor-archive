"""Root-only HTTP surface for persistent provider-chain outage notices."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.dependency.auth import require_root
from app.module.auth.schema.auth_schema import UserSchema
from app.module.knowledge.dependencies import get_provider_notice_service
from app.module.knowledge.schema.provider_notice_schema import (
    ProviderErrorNoticeListSchema,
    ProviderErrorNoticeReadSchema,
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


__all__ = ["router"]
