"""Persistence contracts for accounts and sessions."""

from datetime import datetime
from typing import Protocol

from app.module.auth.model.auth_model import (
    AppUserModel,
    UserProfileCardModel,
    UserSessionModel,
)


class UserRepositoryProtocol(Protocol):
    async def count(self) -> int: ...

    async def count_roots(self) -> int: ...

    async def list_users(self) -> list[AppUserModel]: ...

    async def get_by_username(self, username: str) -> AppUserModel | None: ...

    async def get_by_id(self, user_id: int) -> AppUserModel | None: ...

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
    ) -> AppUserModel: ...

    async def touch_login(self, user: AppUserModel, now: datetime) -> None: ...

    async def update_active(
        self,
        user: AppUserModel,
        *,
        is_active: bool,
        now: datetime,
    ) -> AppUserModel: ...

    async def update_password(
        self,
        user: AppUserModel,
        *,
        password_hash: str,
        must_change_password: bool,
        password_changed_at: datetime,
        now: datetime,
    ) -> AppUserModel: ...

    async def update_display_name(
        self,
        user: AppUserModel,
        *,
        display_name: str,
        now: datetime,
    ) -> AppUserModel: ...

    async def list_profile_cards(self, user_id: int) -> list[UserProfileCardModel]: ...

    async def replace_profile_cards(
        self,
        user_id: int,
        *,
        cards: list[tuple[str, str]],
        now: datetime,
    ) -> list[UserProfileCardModel]: ...


class SessionRepositoryProtocol(Protocol):
    async def add(
        self,
        *,
        token_hash: str,
        user_id: int,
        expires_at: datetime,
    ) -> UserSessionModel: ...

    async def get_by_token_hash(self, token_hash: str) -> UserSessionModel | None: ...

    async def delete_by_token_hash(self, token_hash: str) -> None: ...

    async def delete_by_user_id(self, user_id: int) -> None: ...

    async def delete_others_for_user(self, user_id: int, *, keep_token_hash: str) -> None: ...

    async def delete_expired(self, now: datetime) -> None: ...

    async def touch(self, session: UserSessionModel, now: datetime) -> None: ...
