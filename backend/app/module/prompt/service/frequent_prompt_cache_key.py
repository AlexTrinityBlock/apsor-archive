"""Cache-key construction local to the frequent-prompt slice."""

import hashlib


def frequent_prompt_cache_key(version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key without importing another slice's helper."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{namespace}:{digest}"
