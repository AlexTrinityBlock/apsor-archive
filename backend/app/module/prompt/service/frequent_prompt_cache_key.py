"""Cache-key construction local to the frequent-prompt slice.

Both the value key and the version scope carry the ``u:{user_id}:`` prefix so
one owner's writes can never read or invalidate another owner's snapshot.
"""


def frequent_prompt_cache_key(version: int, namespace: str, user_id: int) -> str:
    """Build a per-user, versioned cache key for the prompt list."""
    return f"apsor:{version}:u:{user_id}:{namespace}"


def frequent_prompt_version_scope(user_id: int, namespace: str) -> str:
    """Return the per-user version scope used to invalidate one prompt list."""
    return f"u:{user_id}:{namespace}"


__all__ = ["frequent_prompt_cache_key", "frequent_prompt_version_scope"]
