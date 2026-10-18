"""Pure account validation rules."""

import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,62}[A-Za-z0-9]$")
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 256


class AuthDomain:
    """Validation rules that do not touch the database or HTTP layer."""

    @staticmethod
    def normalize_username(username: str) -> str:
        return username.strip().lower()

    @staticmethod
    def is_valid_username(username: str) -> bool:
        return bool(USERNAME_PATTERN.fullmatch(username))

    @staticmethod
    def is_valid_password(password: str) -> bool:
        if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
            return False
        return bool(password.strip())
