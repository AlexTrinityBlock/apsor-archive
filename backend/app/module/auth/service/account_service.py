"""Root-only account creation, enable/disable, and password reset."""

import secrets
import string
from typing import cast

from app.module.auth.domain.auth_domain import AuthDomain
from app.module.auth.exception.domain_error import (
    AccountNotFoundError,
    CannotDisableRootError,
    ForbiddenError,
    InvalidProfileError,
    InvalidUsernameError,
    LastRootProtectedError,
    UsernameTakenError,
)
from app.module.auth.model.auth_model import AppUserModel
from app.module.auth.protocol.auth_repository_protocol import (
    SessionRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.module.auth.protocol.security_protocol import PasswordHasherProtocol
from app.module.auth.schema.account_schema import (
    AccountCreateSchema,
    AccountListSchema,
    AccountSchema,
    AccountTemporaryPasswordSchema,
    AccountUsageSchema,
)
from app.module.auth.schema.auth_schema import UserRole
from app.shared.time import utcnow

_TEMPORARY_PASSWORD_LENGTH = 20
_TEMPORARY_PASSWORD_GROUPS = (
    string.ascii_lowercase,
    string.ascii_uppercase,
    string.digits,
    "!@#$%^&*-_=+",
)
_TEMPORARY_PASSWORD_ALPHABET = "".join(_TEMPORARY_PASSWORD_GROUPS)


def _generate_temporary_password() -> str:
    """Build a 20-character password that satisfies the local login policy.

    One character from every class is placed first, the remainder is drawn from
    the full alphabet, and the result is shuffled with the OS-backed generator.
    No character is a whitespace, so the password always passes
    ``AuthDomain.is_valid_password``.
    """
    characters = [secrets.choice(group) for group in _TEMPORARY_PASSWORD_GROUPS]
    characters.extend(
        secrets.choice(_TEMPORARY_PASSWORD_ALPHABET)
        for _ in range(_TEMPORARY_PASSWORD_LENGTH - len(characters))
    )
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


class AccountService:
    """Coordinate the root account lifecycle without deleting identities."""

    def __init__(
        self,
        *,
        user_repository: UserRepositoryProtocol,
        session_repository: SessionRepositoryProtocol,
        password_hasher: PasswordHasherProtocol,
    ) -> None:
        self.user_repository = user_repository
        self.session_repository = session_repository
        self.password_hasher = password_hasher

    @staticmethod
    def _to_schema(user: AppUserModel) -> AccountSchema:
        return AccountSchema(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=cast(UserRole, user.role),
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            usage=AccountUsageSchema(
                prompt_tokens=user.prompt_tokens,
                completion_tokens=user.completion_tokens,
                total_tokens=user.total_tokens,
                cached_tokens=user.cached_tokens,
                api_calls=user.api_calls,
                turns=user.agent_turns,
                last_activity_at=user.last_agent_activity_at,
            ),
        )

    async def _require_account(self, user_id: int) -> AppUserModel:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise AccountNotFoundError(user_id)
        return user

    async def list_accounts(self) -> AccountListSchema:
        """Return root first, then every other account by creation order."""
        users = await self.user_repository.list_users()
        return AccountListSchema(items=[self._to_schema(user) for user in users])

    async def create_account(
        self,
        *,
        actor_user_id: int,
        payload: AccountCreateSchema,
    ) -> AccountTemporaryPasswordSchema:
        """Create a normal user with a one-time temporary password."""
        username = AuthDomain.normalize_username(payload.username)
        if not AuthDomain.is_valid_username(username):
            raise InvalidUsernameError()
        display_name = " ".join(payload.display_name.split())
        if not display_name or len(display_name) > 80:
            raise InvalidProfileError("Display name must contain between 1 and 80 characters.")
        if await self.user_repository.get_by_username(username) is not None:
            raise UsernameTakenError(username)

        temporary_password = _generate_temporary_password()
        user = await self.user_repository.create(
            username,
            self.password_hasher.hash(temporary_password),
            role="user",
            display_name=display_name,
            created_by_user_id=actor_user_id,
            is_active=True,
            must_change_password=True,
        )
        return AccountTemporaryPasswordSchema(
            user=self._to_schema(user),
            temporary_password=temporary_password,
        )

    async def disable_account(
        self,
        *,
        actor_user_id: int,
        user_id: int,
    ) -> AccountSchema:
        """Disable an account and revoke every session it owns."""
        user = await self._require_account(user_id)
        if user.role == "root" and user.id == actor_user_id:
            raise CannotDisableRootError()
        if user.role == "root" and await self.user_repository.count_roots() <= 1:
            raise LastRootProtectedError()

        await self.session_repository.delete_by_user_id(user.id)
        if user.is_active:
            user = await self.user_repository.update_active(user, is_active=False, now=utcnow())
        return self._to_schema(user)

    async def enable_account(self, *, user_id: int) -> AccountSchema:
        """Re-enable an account; the user must log in again."""
        user = await self._require_account(user_id)
        if not user.is_active:
            user = await self.user_repository.update_active(user, is_active=True, now=utcnow())
        return self._to_schema(user)

    async def reset_account_password(
        self,
        *,
        actor_user_id: int,
        user_id: int,
    ) -> AccountTemporaryPasswordSchema:
        """Replace a user's password with a temporary one and revoke its sessions."""
        user = await self._require_account(user_id)
        if user.id == actor_user_id:
            raise ForbiddenError("Use the password change endpoint for your own account.")

        temporary_password = _generate_temporary_password()
        now = utcnow()
        user = await self.user_repository.update_password(
            user,
            password_hash=self.password_hasher.hash(temporary_password),
            must_change_password=True,
            password_changed_at=now,
            now=now,
        )
        await self.session_repository.delete_by_user_id(user.id)
        return AccountTemporaryPasswordSchema(
            user=self._to_schema(user),
            temporary_password=temporary_password,
        )
