"""Auth-domain errors."""


class AuthError(Exception):
    """Base class for authentication failures."""


class AuthenticationRequiredError(AuthError):
    def __init__(self) -> None:
        super().__init__("Authentication is required.")


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid username or password.")


class SetupAlreadyCompleteError(AuthError):
    def __init__(self) -> None:
        super().__init__("The owner account has already been created.")


class InvalidUsernameError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "Username must be 3-64 characters, start and end with a letter or digit, "
            "and contain only letters, digits, dot, dash, or underscore."
        )


class InvalidProfileError(AuthError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class WeakPasswordError(AuthError):
    def __init__(self, detail: str = "Password must be between 10 and 256 characters.") -> None:
        super().__init__(detail)


class PasswordMismatchError(AuthError):
    def __init__(self) -> None:
        super().__init__("The password confirmation does not match.")


class LoginThrottledError(AuthError):
    def __init__(self) -> None:
        super().__init__("Too many login attempts. Try again later.")


class AccountDisabledError(AuthError):
    def __init__(self) -> None:
        super().__init__("This account is disabled.")


class PasswordChangeRequiredError(AuthError):
    def __init__(self) -> None:
        super().__init__("You must change your password before continuing.")


class ForbiddenError(AuthError):
    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(detail)


class CurrentPasswordInvalidError(AuthError):
    def __init__(self) -> None:
        super().__init__("The current password is invalid.")


class AccountNotFoundError(AuthError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"Account {user_id} was not found.")


class UsernameTakenError(AuthError):
    def __init__(self, username: str) -> None:
        super().__init__(f"Username {username} is already taken.")


class CannotDisableRootError(AuthError):
    def __init__(self) -> None:
        super().__init__("The root account cannot be disabled.")


class LastRootProtectedError(AuthError):
    def __init__(self) -> None:
        super().__init__("The only root account must stay enabled.")
