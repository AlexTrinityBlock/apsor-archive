"""Composition root for the chat companion slice."""

from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependency.auth import require_authenticated
from app.infrastructure.database.session import get_db_session
from app.module.auth.schema.auth_schema import UserSchema
from app.module.companion.protocol.companion_protocol import CompanionStorageProtocol
from app.module.companion.repository.companion_repository import CompanionRepository
from app.module.companion.service.companion_service import CompanionService


def get_companion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    user: UserSchema = Depends(require_authenticated),  # noqa: B008
) -> CompanionService:
    """Build the owner-bound companion service on the request transaction."""
    return CompanionService(
        repository=CompanionRepository(session),
        storage=cast(CompanionStorageProtocol, request.app.state.storage),
        user_id=user.user_id,
    )


__all__ = ["get_companion_service"]
