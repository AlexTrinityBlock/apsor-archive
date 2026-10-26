"""Shared browser-session cookie mutations for auth and account routes."""

from fastapi import Response

from app.infrastructure.config.settings import Settings


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Attach the HttpOnly session cookie used by every sign-in flow."""
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
