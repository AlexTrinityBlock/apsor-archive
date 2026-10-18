"""Pure contract for encrypting secrets at rest."""

from typing import Protocol


class SecretCipherProtocol(Protocol):
    """Encrypt, decrypt, and mask a secret without exposing it."""

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...

    def hint(self, plaintext: str) -> str: ...
