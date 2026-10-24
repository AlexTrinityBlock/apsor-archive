"""SQLAlchemy persistence for the account and its sessions."""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.auth.model.auth_model import AppUserModel, UserSessionModel
from app.shared.time import utcnow


class UserRepository:
    """Queries over the single owner account."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(AppUserModel.id)))).scalar_one())

    async def get_by_username(self, username: str) -> AppUserModel | None:
        statement = select(AppUserModel).where(AppUserModel.username == username)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> AppUserModel | None:
        return await self.session.get(AppUserModel, user_id)

    async def create(self, username: str, password_hash: str) -> AppUserModel:
        user = AppUserModel(username=username, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def touch_login(self, user: AppUserModel, now: datetime) -> None:
        user.last_login_at = now
        user.updated_at = now
        self.session.add(user)
        await self.session.flush()


class SessionRepository:
    """Queries over browser sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        token_hash: str,
        user_id: int,
        expires_at: datetime,
    ) -> UserSessionModel:
        session = UserSessionModel(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at,
            created_at=utcnow(),
            last_seen_at=utcnow(),
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_by_token_hash(self, token_hash: str) -> UserSessionModel | None:
        statement = select(UserSessionModel).where(UserSessionModel.token_hash == token_hash)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def delete_by_token_hash(self, token_hash: str) -> None:
        await self.session.execute(
            delete(UserSessionModel).where(UserSessionModel.token_hash == token_hash)
        )

    async def delete_expired(self, now: datetime) -> None:
        await self.session.execute(
            delete(UserSessionModel).where(UserSessionModel.expires_at < now)
        )

    async def touch(self, user_session: UserSessionModel, now: datetime) -> None:
        user_session.last_seen_at = now
        self.session.add(user_session)
        await self.session.flush()
