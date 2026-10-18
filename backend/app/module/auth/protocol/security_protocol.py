"""Password hashing and session token contracts."""

from typing import Protocol


class PasswordHasherProtocol(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class SessionTokenProtocol(Protocol):
    def generate(self) -> str: ...

    def hash(self, token: str) -> str: ...
