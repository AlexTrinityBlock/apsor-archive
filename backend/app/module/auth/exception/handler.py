"""Register auth-domain errors with the global exception registry."""

from app.module.auth.exception.domain_error import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    InvalidUsernameError,
    LoginThrottledError,
    PasswordMismatchError,
    SetupAlreadyCompleteError,
    WeakPasswordError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    ExceptionRegistry.register(AuthenticationRequiredError, 401, "authentication_required")
    ExceptionRegistry.register(InvalidCredentialsError, 401, "invalid_credentials")
    ExceptionRegistry.register(SetupAlreadyCompleteError, 409, "setup_already_complete")
    ExceptionRegistry.register(InvalidUsernameError, 422, "invalid_username")
    ExceptionRegistry.register(WeakPasswordError, 422, "weak_password")
    ExceptionRegistry.register(PasswordMismatchError, 422, "password_mismatch")
    ExceptionRegistry.register(LoginThrottledError, 429, "login_throttled")
