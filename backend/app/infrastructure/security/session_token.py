"""Opaque session tokens; only their SHA-256 hash is stored."""

import hashlib
import secrets


class SessionTokenGenerator:
    """Generate a browser token and a one-way database key."""

    def generate(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
