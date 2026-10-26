"""Register auth-domain errors with the global exception registry."""

from app.module.auth.exception.domain_error import (
    AccountDisabledError,
    AccountNotFoundError,
    AuthenticationRequiredError,
    CannotDisableRootError,
    CurrentPasswordInvalidError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidProfileError,
    InvalidUsernameError,
    LastRootProtectedError,
    LoginThrottledError,
    PasswordChangeRequiredError,
    PasswordMismatchError,
    SetupAlreadyCompleteError,
    UsernameTakenError,
    WeakPasswordError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    ExceptionRegistry.register(AuthenticationRequiredError, 401, "authentication_required")
    ExceptionRegistry.register(InvalidCredentialsError, 401, "invalid_credentials")
    ExceptionRegistry.register(CurrentPasswordInvalidError, 400, "current_password_invalid")
    ExceptionRegistry.register(AccountDisabledError, 403, "account_disabled")
    ExceptionRegistry.register(PasswordChangeRequiredError, 403, "password_change_required")
    ExceptionRegistry.register(ForbiddenError, 403, "forbidden")
    ExceptionRegistry.register(AccountNotFoundError, 404, "account_not_found")
    ExceptionRegistry.register(SetupAlreadyCompleteError, 409, "setup_already_complete")
    ExceptionRegistry.register(UsernameTakenError, 409, "username_taken")
    ExceptionRegistry.register(CannotDisableRootError, 409, "cannot_disable_root")
    ExceptionRegistry.register(LastRootProtectedError, 409, "last_root_protected")
    ExceptionRegistry.register(InvalidUsernameError, 422, "invalid_username")
    ExceptionRegistry.register(InvalidProfileError, 422, "invalid_profile")
    ExceptionRegistry.register(WeakPasswordError, 422, "weak_password")
    ExceptionRegistry.register(PasswordMismatchError, 422, "password_mismatch")
    ExceptionRegistry.register(LoginThrottledError, 429, "login_throttled")
