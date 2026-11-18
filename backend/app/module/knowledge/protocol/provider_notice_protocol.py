"""Provider failure events passed from fallback clients to the notice service.

The fallback wrappers only know provider/transport failures, never archive
content. They build one immutable event after an entire chain fails and hand it
to an optional asynchronous reporter. The knowledge slice persists a sanitized
copy so root can see that a capability is down.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.module.knowledge.domain.provider_config_domain import ProviderCapability


@dataclass(frozen=True)
class ProviderAttempt:
    """One failed chain entry, in the order it was attempted."""

    provider: str
    status_code: int | None
    error_code: str | None
    detail: str


@dataclass(frozen=True)
class ProviderFailureEvent:
    """The whole chain failed for one operation."""

    capability: ProviderCapability
    operation: str
    error_code: str
    status_code: int | None
    detail: str
    attempts: tuple[ProviderAttempt, ...] = field(default_factory=tuple)


type ProviderFailureReporter = Callable[[ProviderFailureEvent], Awaitable[None]]


class ProviderFailureReporterProtocol(Protocol):
    """Structural reporter accepted by the fallback wrappers."""

    async def report(self, event: ProviderFailureEvent) -> None: ...


__all__ = [
    "ProviderAttempt",
    "ProviderFailureEvent",
    "ProviderFailureReporter",
    "ProviderFailureReporterProtocol",
]
