"""Pure rules for filling in chunk embeddings that could not be computed.

A chunk whose ``embedding`` is NULL is *pending*: its text and n-grams are
already indexed, so keyword (BM25) search finds it, but the vector lane does
not until a later pass embeds it. Pending rows appear whenever the provider is
out of credits, rejects the key, is unreachable, or the account's own embedding
allowance is spent. The worker's backfill loop retries them automatically.

Two kinds of failure are told apart:

* **Systemic** failures say nothing about the text itself (billing, quota,
  authentication, rate limits, outages, network errors). They trip a global
  circuit breaker with exponential backoff and never count against a chunk, so
  every row resumes once credits or the key are fixed.
* **Per-chunk** failures (HTTP 400, 413, 422 on a single input) mean this text
  cannot be embedded as is. They increment the chunk's ``embedding_failures``
  counter; at :data:`MAX_EMBEDDING_FAILURES` the row stops being retried so one
  poison chunk cannot loop forever. It stays searchable by keywords.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MAX_EMBEDDING_FAILURES = 5

# Statuses that blame the submitted text rather than the provider or account.
PER_CHUNK_STATUS_CODES = frozenset({400, 413, 422})

BREAKER_BASE_SECONDS = 30.0
BREAKER_MAX_SECONDS = 30 * 60.0


def is_per_chunk_failure(status_code: int | None) -> bool:
    """Return whether an embedding error blames the input text."""
    return status_code in PER_CHUNK_STATUS_CODES


def failure_code(status_code: int | None) -> str:
    """Return a stable, content-free code for logs and the status endpoint."""
    if status_code is None:
        return "provider_unreachable"
    if status_code in (401, 403):
        return "provider_auth"
    if status_code == 402:
        return "provider_billing"
    if status_code == 429:
        return "provider_quota"
    if status_code >= 500:
        return "provider_unavailable"
    return f"provider_http_{status_code}"


def backoff_seconds(consecutive_failures: int) -> float:
    """Exponential backoff: 30 s, 60 s, 120 s ... capped at 30 minutes."""
    exponent = max(0, consecutive_failures - 1)
    return min(BREAKER_MAX_SECONDS, BREAKER_BASE_SECONDS * (2.0**exponent))


@dataclass
class CircuitBreaker:
    """Global pause after systemic provider failures.

    ``trip`` opens the breaker for a growing interval. ``reset`` closes it at
    once (a successful batch, a provider configuration change, or a root
    "retry now" nudge).
    """

    consecutive_failures: int = 0
    open_until: datetime | None = None
    last_error_code: str | None = None
    tripped_at: datetime | None = None

    def is_open(self, now: datetime) -> bool:
        return self.open_until is not None and now < self.open_until

    def trip(self, code: str, now: datetime) -> datetime:
        self.consecutive_failures += 1
        self.last_error_code = code
        self.tripped_at = now
        self.open_until = now + timedelta(seconds=backoff_seconds(self.consecutive_failures))
        return self.open_until

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.open_until = None
        self.last_error_code = None
        self.tripped_at = None


def utc_now() -> datetime:
    """Return an aware UTC timestamp (a seam for tests)."""
    return datetime.now(UTC)


__all__ = [
    "BREAKER_BASE_SECONDS",
    "BREAKER_MAX_SECONDS",
    "MAX_EMBEDDING_FAILURES",
    "PER_CHUNK_STATUS_CODES",
    "CircuitBreaker",
    "backoff_seconds",
    "failure_code",
    "is_per_chunk_failure",
    "utc_now",
]
