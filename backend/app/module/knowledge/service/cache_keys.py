"""Cache key and version-scope construction.

Private archive reads are cached inside a per-user namespace. Global
configuration caches (the provider registry) keep the unprefixed key because
every account reads the same rows.
"""

import hashlib

DEFAULT_INDEX_SCOPE = "index"


def cache_key(version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key for global, non-private configuration."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{namespace}:{digest}"


def user_cache_key(user_id: int, version: int, namespace: str, *parts: str) -> str:
    """Build a versioned cache key inside one account's private namespace."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"apsor:u:{user_id}:{version}:{namespace}:{digest}"


def user_version_scope(user_id: int, scope: str = DEFAULT_INDEX_SCOPE) -> str:
    """Return the cache version scope for one account.

    The cache implementation prefixes scopes with ``apsor:`` and suffixes them
    with ``:version``, so this yields ``apsor:u:{user_id}:{scope}:version``.
    """
    return f"u:{user_id}:{scope}"
