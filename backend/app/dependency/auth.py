"""Global authentication dependencies used by protected routers."""

from fastapi import Depends, Request

from app.module.auth.dependencies import (
    get_auth_service,
    get_auth_settings,
    get_cookie_token,
)
from app.module.auth.schema.auth_schema import UserSchema
from app.module.auth.service.auth_service import AuthService


async def get_current_user(
    request: Request,
    token: str | None = Depends(get_cookie_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserSchema:
    """Resolve the HttpOnly session cookie into a user or raise 401."""
    settings = get_auth_settings(request)
    if token is None:
        token = request.cookies.get(settings.cookie_name)
    return await auth_service.resolve_session(token)


async def require_authenticated(
    user: UserSchema = Depends(get_current_user),
) -> UserSchema:
    """A router-level guard; the returned user is the authenticated principal."""
    return user
