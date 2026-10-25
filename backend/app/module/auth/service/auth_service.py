"""Owner-account setup, login, session resolution, and throttling."""

import threading
import time
from datetime import timedelta

from app.module.auth.domain.auth_domain import AuthDomain
from app.module.auth.exception.domain_error import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    InvalidProfileError,
    InvalidUsernameError,
    LoginThrottledError,
    PasswordMismatchError,
    SetupAlreadyCompleteError,
    WeakPasswordError,
)
from app.module.auth.model.auth_model import AppUserModel
from app.module.auth.protocol.auth_repository_protocol import (
    SessionRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.module.auth.protocol.security_protocol import (
    PasswordHasherProtocol,
    SessionTokenProtocol,
)
from app.module.auth.schema.auth_schema import AuthStatusSchema, UserSchema
from app.shared.time import utcnow

# Failed login attempts are process-local. This is a single-user, single-process
# archive; a multi-process deployment should move the counter to Valkey.
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
            bio=user.bio,
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
            self._record_failure(throttle_key)
            raise InvalidCredentialsError()
        self._clear_failures(throttle_key)
        now = utcnow()
        await self.user_repository.touch_login(user, now)
        await self.session_repository.delete_expired(now)
        token = await self._new_session(user)
        return self._to_schema(user), token

    async def update_profile(
        self,
        user_id: int,
        *,
        display_name: str,
        bio: str | None,
    ) -> UserSchema:
        """Update the owner's name and self-introduction in one transaction."""
        cleaned_name = " ".join(display_name.split())
        if not cleaned_name or len(cleaned_name) > 80:
            raise InvalidProfileError("Display name must contain between 1 and 80 characters.")
        cleaned_bio = bio.strip() if isinstance(bio, str) else None
        if cleaned_bio == "":
            cleaned_bio = None
        if cleaned_bio is not None and len(cleaned_bio) > 2000:
            raise InvalidProfileError("Self-introduction cannot exceed 2,000 characters.")
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationRequiredError()
        updated = await self.user_repository.update_profile(
            user,
            display_name=cleaned_name,
            bio=cleaned_bio,
            now=utcnow(),
        )
        return self._to_schema(updated)

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
        except AuthenticationRequiredError:
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
