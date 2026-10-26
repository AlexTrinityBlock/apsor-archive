"""Global authentication and role dependencies used by protected routers."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database, apply_user_context, get_db_session
from app.module.auth.dependencies import (
    build_auth_service,
    get_auth_service,
    get_auth_settings,
    get_cookie_token,
)
from app.module.auth.exception.domain_error import (
    AccountDisabledError,
    ForbiddenError,
    PasswordChangeRequiredError,
)
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.auth_service import AuthService


async def get_current_user(
    request: Request,
    token: str | None = Depends(get_cookie_token),
    auth_service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_db_session),
) -> UserSchema:
    """Resolve the HttpOnly session cookie and scope the transaction to its owner.

    Auth tables are deliberately outside row-level security, so the token lookup
    works before a user context exists. Once the session resolves, the same
    request transaction receives ``app.user_id`` and ``app.user_role``.
    """
    settings = get_auth_settings(request)
    if token is None:
        token = request.cookies.get(settings.cookie_name)
    user = await auth_service.resolve_session(token)
    await apply_user_context(session, user.user_id, user.role)
    return user


async def require_stateless_authenticated(
    request: Request,
    token: str | None = Depends(get_cookie_token),
) -> UserSchema:
    """Resolve an account without touching the request-scoped DB session.

    SSE responses keep yield dependencies open until the stream ends. Agent
    routes use this short-lived public session for the cookie lookup, then the
    stream opens its own owner-scoped short transactions for every turn/tool.
    """
    database = cast(Database, request.app.state.db)
    settings = get_auth_settings(request)
    async with database.public_session() as session:
        user = await build_auth_service(session, settings).resolve_session(token)
    if not user.is_active:
        raise AccountDisabledError()
    if user.must_change_password:
        raise PasswordChangeRequiredError()
    return user


async def require_authenticated(
    user: UserSchema = Depends(get_current_user),
) -> UserSchema:
    """A router-level guard for every route that reads private archive data.

    A disabled account is rejected even if a stale session slipped through, and
    a forced password change blocks every protected route except the three auth
    endpoints that deliberately use ``get_current_user`` or no guard at all.
    """
    if not user.is_active:
        raise AccountDisabledError()
    if user.must_change_password:
        raise PasswordChangeRequiredError()
    return user


async def require_root(
    user: UserSchema = Depends(require_authenticated),
) -> UserSchema:
    """Layer the root role on top of the authenticated guard."""
    if user.role != "root":
        raise ForbiddenError()
    return user
