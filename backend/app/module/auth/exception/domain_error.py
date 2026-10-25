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
    def __init__(self) -> None:
        super().__init__("Password must be between 10 and 256 characters.")


class PasswordMismatchError(AuthError):
    def __init__(self) -> None:
        super().__init__("The password confirmation does not match.")


class LoginThrottledError(AuthError):
    def __init__(self) -> None:
        super().__init__("Too many login attempts. Try again later.")
