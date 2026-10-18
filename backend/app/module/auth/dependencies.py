"""Composition root for the auth slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.session_token import SessionTokenGenerator
from app.module.auth.repository.auth_repository import SessionRepository, UserRepository
from app.module.auth.service.auth_service import AuthService


def get_auth_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_cookie_token(
    request: Request,
    settings: Settings = Depends(get_auth_settings),
) -> str | None:
    return request.cookies.get(settings.cookie_name)


def get_auth_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthService:
    settings = get_auth_settings(request)
    return AuthService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
        password_hasher=Argon2PasswordHasher(),
        token_generator=SessionTokenGenerator(),
        session_ttl_hours=settings.session_ttl_hours,
        login_attempt_limit=settings.login_attempt_limit,
        login_window_minutes=settings.login_window_minutes,
    )
