"""Cache key construction with the global index version."""

import hashlib


def cache_key(version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key for a read-heavy endpoint."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"dendro:{version}:{namespace}:{digest}"
