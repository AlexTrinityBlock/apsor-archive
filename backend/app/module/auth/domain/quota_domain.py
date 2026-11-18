"""Per-account usage allowance rules.

Four independent categories share one accounting shape. ``lifetime`` is the
monotonic provider-side counter; ``used_before_reset`` is the value captured by
the last admin reset; the current cycle is ``used = max(0, lifetime - base)``.
A NULL ``granted`` means unlimited. ``enabled`` is an explicit switch and always
wins, including over an unlimited grant.

The field mapping lives here so the admin service, the enforcement service, and
the HTTP projection cannot drift apart.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

QuotaCategory = Literal["chat", "embedding", "web_search", "web_fetch"]

# Fixed presentation and storage order. Account responses always list quotas in
# this order, regardless of the order an operator edited them.
QUOTA_CATEGORIES: tuple[QuotaCategory, ...] = (
    "chat",
    "embedding",
    "web_search",
    "web_fetch",
)


@dataclass(frozen=True)
class QuotaFields:
    """The four ``app_user`` columns that make up one quota category."""

    enabled: str
    granted: str
    used_before_reset: str
    lifetime: str


QUOTA_FIELDS: dict[QuotaCategory, QuotaFields] = {
    "chat": QuotaFields(
        enabled="chat_enabled",
        granted="chat_granted",
        used_before_reset="chat_used_before_reset",
        lifetime="total_tokens",
    ),
    "embedding": QuotaFields(
        enabled="embedding_enabled",
        granted="embedding_granted",
        used_before_reset="embedding_used_before_reset",
        lifetime="embedding_tokens",
    ),
    "web_search": QuotaFields(
        enabled="web_search_enabled",
        granted="web_search_granted",
        used_before_reset="web_search_used_before_reset",
        lifetime="web_search_calls",
    ),
    "web_fetch": QuotaFields(
        enabled="web_fetch_enabled",
        granted="web_fetch_granted",
        used_before_reset="web_fetch_used_before_reset",
        lifetime="web_fetch_calls",
    ),
}


class QuotaRow(Protocol):
    """Any row exposing the mapped ``app_user`` attributes."""

    chat_enabled: bool
    chat_granted: int | None
    chat_used_before_reset: int
    total_tokens: int
    embedding_tokens: int
    embedding_enabled: bool
    embedding_granted: int | None
    embedding_used_before_reset: int
    web_search_calls: int
    web_search_enabled: bool
    web_search_granted: int | None
    web_search_used_before_reset: int
    web_fetch_calls: int
    web_fetch_enabled: bool
    web_fetch_granted: int | None
    web_fetch_used_before_reset: int


def parse_quota_category(value: str) -> QuotaCategory:
    """Validate an untrusted category name.

    The caller converts a failure into its own domain error; the quota domain
    stays free of HTTP and slice-specific exception imports.
    """
    if value not in QUOTA_CATEGORIES:
        raise ValueError(f"Unknown usage category: {value!r}")
    return value


def quota_lifetime(row: QuotaRow, category: QuotaCategory) -> int:
    """Return the monotonic lifetime counter for one category."""
    value = getattr(row, QUOTA_FIELDS[category].lifetime)
    return max(0, int(value))


def quota_base(row: QuotaRow, category: QuotaCategory) -> int:
    """Return the lifetime value captured by the last reset."""
    value = getattr(row, QUOTA_FIELDS[category].used_before_reset)
    return max(0, int(value))


def quota_used(row: QuotaRow, category: QuotaCategory) -> int:
    """Return the current cycle's usage: lifetime minus the last reset base."""
    return max(0, quota_lifetime(row, category) - quota_base(row, category))


def quota_granted(row: QuotaRow, category: QuotaCategory) -> int | None:
    """Return the finite grant, or ``None`` for an unlimited allowance."""
    value = getattr(row, QUOTA_FIELDS[category].granted)
    return None if value is None else max(0, int(value))


def quota_enabled(row: QuotaRow, category: QuotaCategory) -> bool:
    """Return the explicit enabled switch."""
    return bool(getattr(row, QUOTA_FIELDS[category].enabled))


def quota_remaining(row: QuotaRow, category: QuotaCategory) -> int | None:
    """Return the headroom left in this cycle, or ``None`` when unlimited.

    Remaining usage clamps at zero so a grant lowered below the current usage
    never reports a negative number.
    """
    granted = quota_granted(row, category)
    if granted is None:
        return None
    return max(0, granted - quota_used(row, category))


def quota_allows(row: QuotaRow, category: QuotaCategory, units: int = 0) -> bool:
    """Return whether one request of ``units`` fits in the allowance.

    A disabled category always blocks. An unlimited grant permits any request.
    A finite grant permits a request while ``used + units <= granted``. Chat
    passes zero units but must still reject a fully consumed grant, so it uses
    :func:`quota_chat_allowed` instead of relying on this boundary.
    """
    if not quota_enabled(row, category):
        return False
    granted = quota_granted(row, category)
    if granted is None:
        return True
    return quota_used(row, category) + max(0, units) <= granted


def quota_chat_allowed(row: QuotaRow) -> bool:
    """Return whether another chat step may start.

    Chat is measured after the provider call, so a fully consumed grant blocks
    the next step (``used >= granted``) rather than fitting one more call.
    """
    if not quota_enabled(row, "chat"):
        return False
    granted = quota_granted(row, "chat")
    if granted is None:
        return True
    return quota_used(row, "chat") < granted


__all__ = [
    "QUOTA_CATEGORIES",
    "QUOTA_FIELDS",
    "QuotaCategory",
    "QuotaFields",
    "QuotaRow",
    "parse_quota_category",
    "quota_allows",
    "quota_base",
    "quota_chat_allowed",
    "quota_enabled",
    "quota_granted",
    "quota_lifetime",
    "quota_remaining",
    "quota_used",
]
