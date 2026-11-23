"""Composition root for the auth slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config.settings import Settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.session_token import SessionTokenGenerator
from app.module.auth.repository.auth_repository import SessionRepository, UserRepository
from app.module.auth.service.account_service import AccountService
from app.module.auth.service.auth_service import AuthService
from app.module.knowledge.model.provider_config_model import ChatProviderConfigModel


def get_auth_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_cookie_token(
    request: Request,
    settings: Settings = Depends(get_auth_settings),
) -> str | None:
    return request.cookies.get(settings.cookie_name)


def build_auth_service(session: AsyncSession, settings: Settings) -> AuthService:
    """Build the auth service on an explicit session.

    Streaming routes use this with a short-lived public session so they do not
    pin the request transaction for the lifetime of an SSE response.
    """
    return AuthService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
        password_hasher=Argon2PasswordHasher(),
        token_generator=SessionTokenGenerator(),
        session_ttl_hours=settings.session_ttl_hours,
        login_attempt_limit=settings.login_attempt_limit,
        login_window_minutes=settings.login_window_minutes,
    )


def get_auth_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthService:
    return build_auth_service(session, get_auth_settings(request))


class ChatProviderDefaults:
    """Resolve the deployment's primary chat endpoint for new accounts.

    This adapter lives in the auth composition root because it reads the
    knowledge slice's provider table. ``AccountService`` only sees the narrow
    ``ChatDefaultsProtocol``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def primary_endpoint(self) -> tuple[int, str] | None:
        row = (
            await self._session.execute(
                select(
                    ChatProviderConfigModel.id,
                    ChatProviderConfigModel.model,
                )
                .where(
                    ChatProviderConfigModel.is_active.is_(True),
                    ChatProviderConfigModel.provider != "none",
                )
                .order_by(
                    ChatProviderConfigModel.priority,
                    ChatProviderConfigModel.id,
                )
                .limit(1)
            )
        ).first()
        if row is None or not row.model:
            return None
        return (int(row.id), str(row.model))


def get_account_service(
    session: AsyncSession = Depends(get_db_session),
) -> AccountService:
    """Assemble the root-only account management service."""
    return AccountService(
        user_repository=UserRepository(session),
        session_repository=SessionRepository(session),
        password_hasher=Argon2PasswordHasher(),
        chat_defaults=ChatProviderDefaults(session),
    )
