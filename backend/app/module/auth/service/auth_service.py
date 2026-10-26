"""Account setup, login, password change, session resolution, and throttling."""

import threading
import time
from datetime import timedelta
from typing import cast

from app.module.auth.domain.auth_domain import AuthDomain
from app.module.auth.exception.domain_error import (
    AccountDisabledError,
    AuthenticationRequiredError,
    CurrentPasswordInvalidError,
    InvalidCredentialsError,
    InvalidProfileError,
    InvalidUsernameError,
    LoginThrottledError,
    PasswordMismatchError,
    SetupAlreadyCompleteError,
    WeakPasswordError,
)
from app.module.auth.model.auth_model import AppUserModel, UserProfileCardModel
from app.module.auth.protocol.auth_repository_protocol import (
    SessionRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.module.auth.protocol.security_protocol import (
    PasswordHasherProtocol,
    SessionTokenProtocol,
)
from app.module.auth.schema.auth_schema import (
    AuthStatusSchema,
    UserProfileCardSchema,
    UserProfileSchema,
    UserProfileUpdateSchema,
    UserRole,
    UserSchema,
)
from app.shared.time import utcnow

# Failed login attempts are process-local. The archive is served by one API
# process; a multi-process deployment should move the counter to Valkey.
_attempts: dict[str, list[float]] = {}
_attempt_lock = threading.Lock()


class AuthService:
    """Coordinate password verification, sessions, and the first-run setup."""

    def __init__(
        self,
        *,
        user_repository: UserRepositoryProtocol,
        session_repository: SessionRepositoryProtocol,
        password_hasher: PasswordHasherProtocol,
        token_generator: SessionTokenProtocol,
        session_ttl_hours: int,
        login_attempt_limit: int,
        login_window_minutes: int,
    ) -> None:
        self.user_repository = user_repository
        self.session_repository = session_repository
        self.password_hasher = password_hasher
        self.token_generator = token_generator
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.login_attempt_limit = login_attempt_limit
        self.login_window_seconds = login_window_minutes * 60

    @staticmethod
    def _to_schema(user: AppUserModel) -> UserSchema:
        return UserSchema(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=cast(UserRole, user.role),
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )

    def _check_throttle(self, key: str) -> None:
        now = time.monotonic()
        with _attempt_lock:
            attempts = [
                attempt
                for attempt in _attempts.get(key, [])
                if now - attempt < self.login_window_seconds
            ]
            _attempts[key] = attempts
            if len(attempts) >= self.login_attempt_limit:
                raise LoginThrottledError()

    def _record_failure(self, key: str) -> None:
        with _attempt_lock:
            _attempts.setdefault(key, []).append(time.monotonic())

    def _clear_failures(self, key: str) -> None:
        with _attempt_lock:
            _attempts.pop(key, None)

    async def _new_session(self, user: AppUserModel) -> str:
        token = self.token_generator.generate()
        await self.session_repository.add(
            token_hash=self.token_generator.hash(token),
            user_id=user.id,
            expires_at=utcnow() + self.session_ttl,
        )
        return token

    async def setup(
        self,
        *,
        username: str,
        password: str,
        confirm_password: str,
    ) -> tuple[UserSchema, str]:
        """Create the owner account on the first run and sign it in."""
        if await self.user_repository.count() > 0:
            raise SetupAlreadyCompleteError()
        normalized = AuthDomain.normalize_username(username)
        if not AuthDomain.is_valid_username(normalized):
            raise InvalidUsernameError()
        if not AuthDomain.is_valid_password(password):
            raise WeakPasswordError()
        if password != confirm_password:
            raise PasswordMismatchError()
        user = await self.user_repository.create(
            normalized,
            self.password_hasher.hash(password),
            role="root",
            is_active=True,
            must_change_password=False,
        )
        await self.user_repository.touch_login(user, utcnow())
        token = await self._new_session(user)
        return self._to_schema(user), token

    async def login(
        self,
        *,
        username: str,
        password: str,
        remote_address: str,
    ) -> tuple[UserSchema, str]:
        """Verify credentials and issue a new opaque session."""
        normalized = AuthDomain.normalize_username(username)
        throttle_key = f"{remote_address}:{normalized}"
        self._check_throttle(throttle_key)
        user = await self.user_repository.get_by_username(normalized)
        if user is None or not self.password_hasher.verify(user.password_hash, password):
            # Unknown usernames and wrong passwords share one response. A disabled
            # account is only revealed after the correct password is supplied.
            self._record_failure(throttle_key)
            raise InvalidCredentialsError()
        if not user.is_active:
            self._clear_failures(throttle_key)
            raise AccountDisabledError()
        self._clear_failures(throttle_key)
        now = utcnow()
        await self.user_repository.touch_login(user, now)
        await self.session_repository.delete_expired(now)
        token = await self._new_session(user)
        return self._to_schema(user), token

    async def change_password(
        self,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
        confirm_password: str,
        current_token: str | None,
    ) -> None:
        """Change the signed-in password and keep only the current session."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationRequiredError()
        if not self.password_hasher.verify(user.password_hash, current_password):
            raise CurrentPasswordInvalidError()
        if not AuthDomain.is_valid_password(new_password):
            raise WeakPasswordError()
        if new_password != confirm_password:
            raise PasswordMismatchError()
        if new_password == current_password:
            raise WeakPasswordError(
                "Choose a new password that differs from the current password."
            )

        now = utcnow()
        await self.user_repository.update_password(
            user,
            password_hash=self.password_hasher.hash(new_password),
            must_change_password=False,
            password_changed_at=now,
            now=now,
        )
        if current_token:
            await self.session_repository.delete_others_for_user(
                user.id,
                keep_token_hash=self.token_generator.hash(current_token),
            )
        else:
            await self.session_repository.delete_by_user_id(user.id)

    @staticmethod
    def _profile_schema(
        user: AppUserModel,
        cards: list[UserProfileCardModel],
    ) -> UserProfileSchema:
        return UserProfileSchema(
            display_name=user.display_name or user.username,
            cards=[
                UserProfileCardSchema(
                    card_id=card.id,
                    title=card.title,
                    content=card.content,
                    sort_order=card.sort_order,
                )
                for card in cards
            ],
        )

    async def get_profile(self, user_id: int) -> UserProfileSchema:
        """Return the effective display name and every ordered profile card."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationRequiredError()
        cards = await self.user_repository.list_profile_cards(user_id)
        return self._profile_schema(user, cards)

    async def update_profile(
        self,
        user_id: int,
        payload: UserProfileUpdateSchema,
    ) -> UserProfileSchema:
        """Replace the display name and every card in one request transaction."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationRequiredError()

        cleaned_name = " ".join(payload.display_name.split())
        if not cleaned_name or len(cleaned_name) > 80:
            raise InvalidProfileError("Display name must contain between 1 and 80 characters.")

        cleaned_cards: list[tuple[str, str]] = []
        for card in payload.cards:
            title = " ".join(card.title.split())
            content = card.content.strip()
            if not title or not content:
                raise InvalidProfileError("Every profile card needs a title and content.")
            if len(title) > 120 or len(content) > 2000:
                raise InvalidProfileError("A profile card exceeds its length limit.")
            cleaned_cards.append((title, content))

        now = utcnow()
        updated = await self.user_repository.update_display_name(
            user,
            display_name=cleaned_name,
            now=now,
        )
        rows = await self.user_repository.replace_profile_cards(
            user_id,
            cards=cleaned_cards,
            now=now,
        )
        return self._profile_schema(updated, rows)

    async def resolve_session(self, token: str | None) -> UserSchema:
        """Return the signed-in user or raise a 401 domain error."""
        if not token:
            raise AuthenticationRequiredError()
        token_hash = self.token_generator.hash(token)
        user_session = await self.session_repository.get_by_token_hash(token_hash)
        now = utcnow()
        if user_session is None:
            raise AuthenticationRequiredError()
        if user_session.expires_at <= now:
            await self.session_repository.delete_by_token_hash(token_hash)
            raise AuthenticationRequiredError()
        user = await self.user_repository.get_by_id(user_session.user_id)
        if user is None:
            await self.session_repository.delete_by_token_hash(token_hash)
            raise AuthenticationRequiredError()
        if not user.is_active:
            await self.session_repository.delete_by_token_hash(token_hash)
            raise AccountDisabledError()
        # must_change_password is intentionally not rejected here; the request
        # guard decides which routes remain reachable while a change is forced.
        if now - user_session.last_seen_at > timedelta(hours=1):
            await self.session_repository.touch(user_session, now)
        return self._to_schema(user)

    async def logout(self, token: str | None) -> None:
        if token:
            await self.session_repository.delete_by_token_hash(self.token_generator.hash(token))

    async def status(self, token: str | None) -> AuthStatusSchema:
        requires_setup = await self.user_repository.count() == 0
        if requires_setup:
            return AuthStatusSchema(
                requires_setup=True,
                authenticated=False,
                user=None,
            )
        if not token:
            return AuthStatusSchema(
                requires_setup=False,
                authenticated=False,
                user=None,
            )
        try:
            user = await self.resolve_session(token)
        except (AuthenticationRequiredError, AccountDisabledError):
            return AuthStatusSchema(
                requires_setup=False,
                authenticated=False,
                user=None,
            )
        return AuthStatusSchema(
            requires_setup=False,
            authenticated=True,
            user=user,
        )

    async def me(self, token: str | None) -> UserSchema:
        return await self.resolve_session(token)
