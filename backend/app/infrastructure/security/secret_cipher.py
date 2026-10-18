"""Fernet encryption for API keys stored in the database."""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from app.infrastructure.config.settings import Settings


class SecretCipherError(Exception):
    """Raised when a stored secret cannot be decrypted."""


class SecretCipher:
    """A small wrapper around Fernet with a local master-key fallback."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_settings(cls, settings: Settings) -> "SecretCipher":
        """Use DENDRO_SECRET_KEY, or create a 0600 key file in the data dir."""
        if settings.secret_key is not None:
            raw = settings.secret_key.get_secret_value().strip()
            if raw:
                key = _normalize_key(raw)
                return cls(key)

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        key_path = settings.data_dir / ".secret_key"
        if key_path.is_file():
            return cls(key_path.read_bytes().strip())
        key = Fernet.generate_key()
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise SecretCipherError("The stored secret cannot be decrypted.") from exc

    def hint(self, plaintext: str) -> str:
        compact = plaintext.strip()
        if len(compact) < 4:
            return "...set"
        return f"...{compact[-4:]}"


def _normalize_key(raw: str) -> bytes:
    """Accept a Fernet key or derive one from an arbitrary passphrase."""
    candidate = raw.encode("ascii", errors="ignore")
    try:
        decoded = base64.urlsafe_b64decode(candidate)
    except Exception:
        decoded = b""
    if len(decoded) == 32:
        return candidate
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
