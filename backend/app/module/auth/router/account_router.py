"""HTTP adapters for root-only account management."""

from fastapi import APIRouter, Depends, Response, status

from app.dependency.auth import require_root
from app.module.auth.dependencies import get_account_service
from app.module.auth.schema.account_schema import (
    AccountCreateSchema,
    AccountListSchema,
    AccountSchema,
    AccountTemporaryPasswordSchema,
)
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.account_service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListSchema, operation_id="listAccounts")
async def list_accounts(
    _root: UserSchema = Depends(require_root),
    service: AccountService = Depends(get_account_service),
) -> AccountListSchema:
    """List every account; the root row is always first."""
    return await service.list_accounts()


@router.post(
    "",
    response_model=AccountTemporaryPasswordSchema,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAccount",
)
async def create_account(
    payload: AccountCreateSchema,
    response: Response,
    root: UserSchema = Depends(require_root),
    service: AccountService = Depends(get_account_service),
) -> AccountTemporaryPasswordSchema:
    """Create a normal user and return its one-time temporary password."""
    response.headers["Cache-Control"] = "no-store"
    return await service.create_account(actor_user_id=root.user_id, payload=payload)


@router.post(
    "/{user_id}/disable",
    response_model=AccountSchema,
    operation_id="disableAccount",
)
async def disable_account(
    user_id: int,
    root: UserSchema = Depends(require_root),
    service: AccountService = Depends(get_account_service),
) -> AccountSchema:
    """Disable an account and revoke every session it owns."""
    return await service.disable_account(actor_user_id=root.user_id, user_id=user_id)


@router.post(
    "/{user_id}/enable",
    response_model=AccountSchema,
    operation_id="enableAccount",
)
async def enable_account(
    user_id: int,
    _root: UserSchema = Depends(require_root),
    service: AccountService = Depends(get_account_service),
) -> AccountSchema:
    """Enable a disabled account without issuing a session."""
    return await service.enable_account(user_id=user_id)


@router.post(
    "/{user_id}/reset-password",
    response_model=AccountTemporaryPasswordSchema,
    operation_id="resetAccountPassword",
)
async def reset_account_password(
    user_id: int,
    response: Response,
    root: UserSchema = Depends(require_root),
    service: AccountService = Depends(get_account_service),
) -> AccountTemporaryPasswordSchema:
    """Replace another user's password with a one-time temporary password."""
    response.headers["Cache-Control"] = "no-store"
    return await service.reset_account_password(actor_user_id=root.user_id, user_id=user_id)
