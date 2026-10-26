"""SQLAlchemy persistence for accounts and their sessions."""

from datetime import datetime

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.auth.model.auth_model import (
    AppUserModel,
    UserProfileCardModel,
    UserSessionModel,
)
from app.shared.time import utcnow


class UserRepository:
    """Queries over every account and its root/user role."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(AppUserModel.id)))).scalar_one())

    async def count_roots(self) -> int:
        statement = select(func.count(AppUserModel.id)).where(AppUserModel.role == "root")
        return int((await self.session.execute(statement)).scalar_one())

    async def list_users(self) -> list[AppUserModel]:
        """List accounts with the single root first, then creation order."""
        statement = select(AppUserModel).order_by(
            case((AppUserModel.role == "root", 0), else_=1),
            AppUserModel.created_at,
            AppUserModel.id,
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_by_username(self, username: str) -> AppUserModel | None:
        statement = select(AppUserModel).where(AppUserModel.username == username)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> AppUserModel | None:
        return await self.session.get(AppUserModel, user_id)

    async def create(
        self,
        username: str,
        password_hash: str,
        *,
        role: str = "user",
        display_name: str | None = None,
        created_by_user_id: int | None = None,
        is_active: bool = True,
        must_change_password: bool = False,
    ) -> AppUserModel:
        user = AppUserModel(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            must_change_password=must_change_password,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def touch_login(self, user: AppUserModel, now: datetime) -> None:
        user.last_login_at = now
        user.updated_at = now
        self.session.add(user)
        await self.session.flush()

    async def update_active(
        self,
        user: AppUserModel,
        *,
        is_active: bool,
        now: datetime,
    ) -> AppUserModel:
        user.is_active = is_active
        user.disabled_at = None if is_active else now
        user.updated_at = now
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_password(
        self,
        user: AppUserModel,
        *,
        password_hash: str,
        must_change_password: bool,
        password_changed_at: datetime,
        now: datetime,
    ) -> AppUserModel:
        user.password_hash = password_hash
        user.must_change_password = must_change_password
        user.password_changed_at = password_changed_at
        user.updated_at = now
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_display_name(
        self,
        user: AppUserModel,
        *,
        display_name: str,
        now: datetime,
    ) -> AppUserModel:
        user.display_name = display_name
        user.updated_at = now
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_profile_cards(self, user_id: int) -> list[UserProfileCardModel]:
        statement = (
            select(UserProfileCardModel)
            .where(UserProfileCardModel.user_id == user_id)
            .order_by(UserProfileCardModel.sort_order, UserProfileCardModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def replace_profile_cards(
        self,
        user_id: int,
        *,
        cards: list[tuple[str, str]],
        now: datetime,
    ) -> list[UserProfileCardModel]:
        """Replace every card in one transaction; new ids are stable for the request."""
        await self.session.execute(
            delete(UserProfileCardModel).where(UserProfileCardModel.user_id == user_id)
        )
        rows = [
            UserProfileCardModel(
                user_id=user_id,
                title=title,
                content=content,
                sort_order=(index + 1) * 10,
                created_at=now,
                updated_at=now,
            )
            for index, (title, content) in enumerate(cards)
        ]
        self.session.add_all(rows)
        await self.session.flush()
        return rows


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
        impersonator_user_id: int | None = None,
    ) -> UserSessionModel:
        session = UserSessionModel(
            token_hash=token_hash,
            user_id=user_id,
            impersonator_user_id=impersonator_user_id,
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

    async def delete_by_user_id(self, user_id: int) -> None:
        """Revoke every session owned by one account."""
        await self.session.execute(
            delete(UserSessionModel).where(UserSessionModel.user_id == user_id)
        )

    async def delete_impersonations_for_actor(self, actor_user_id: int) -> None:
        """Revoke every impersonation session started by one account."""
        await self.session.execute(
            delete(UserSessionModel).where(
                UserSessionModel.impersonator_user_id == actor_user_id
            )
        )

    async def delete_others_for_user(self, user_id: int, *, keep_token_hash: str) -> None:
        """Revoke every session except the browser token that changed the password."""
        await self.session.execute(
            delete(UserSessionModel).where(
                UserSessionModel.user_id == user_id,
                UserSessionModel.token_hash != keep_token_hash,
            )
        )

    async def delete_expired(self, now: datetime) -> None:
        await self.session.execute(
            delete(UserSessionModel).where(UserSessionModel.expires_at < now)
        )

    async def touch(self, user_session: UserSessionModel, now: datetime) -> None:
        user_session.last_seen_at = now
        self.session.add(user_session)
        await self.session.flush()
