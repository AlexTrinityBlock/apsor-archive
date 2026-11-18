"""Persist and read sanitized provider-chain outage notices.

The fallback wrappers call :meth:`ProviderErrorNoticeService.report` only after
an entire chain fails. Reporting is best effort and uses its own short-lived
system session so a provider call never holds a database connection.

Notices are deduplicated by ``(capability, operation, error_code)`` while
unresolved and last seen inside a 15-minute window. Every stored string is
sanitized: control characters collapse, credentials and authorization headers
are redacted, and detail is bounded. The table never stores prompts, documents,
or other archive content.
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.session import system_session
from app.module.knowledge.domain.provider_config_domain import PROVIDER_CAPABILITIES
from app.module.knowledge.exception.domain_error import ProviderNoticeNotFoundError
from app.module.knowledge.model.provider_error_notice_model import (
    ProviderErrorNoticeModel,
)
from app.module.knowledge.protocol.provider_notice_protocol import (
    ProviderFailureEvent,
)
from app.module.knowledge.repository.provider_error_notice_repository import (
    ProviderErrorNoticeRepository,
)
from app.module.knowledge.schema.provider_notice_schema import (
    ProviderAttemptSchema,
    ProviderErrorNoticeListSchema,
    ProviderErrorNoticeReadSchema,
)
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

DEFAULT_DEDUPE_WINDOW = timedelta(minutes=15)
_DETAIL_LIMIT = 2_000
_ATTEMPT_DETAIL_LIMIT = 400
_ERROR_CODE_LIMIT = 64
_LABEL_LIMIT = 32

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL_CREDENTIALS = re.compile(r"(https?://)[^/\s@]+@", re.IGNORECASE)
_AUTHORIZATION = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*\S+",
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret|token|password)\b\s*[:=]\s*\S+",
)
_KEY_PREFIXES = re.compile(
    r"\b(sk|tvly|exa|gsk|xai|ds)-[A-Za-z0-9_-]{8,}",
    re.IGNORECASE,
)

_SAFE_CAPABILITIES = frozenset(PROVIDER_CAPABILITIES)


def _collapse(value: str, limit: int) -> str:
    """Strip control characters, collapse whitespace, and cap one string."""
    cleaned = _CONTROL_CHARS.sub(" ", value)
    cleaned = _BEARER.sub("bearer [redacted]", cleaned)
    cleaned = _AUTHORIZATION.sub("authorization=[redacted]", cleaned)
    cleaned = _SECRET_ASSIGNMENT.sub(r"\1=[redacted]", cleaned)
    cleaned = _URL_CREDENTIALS.sub(r"\1[redacted]@", cleaned)
    cleaned = _KEY_PREFIXES.sub("[redacted]", cleaned)
    return " ".join(cleaned.split())[:limit]


class ProviderErrorNoticeService:
    """Global operational notices built on one database session factory."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        dedupe_window: timedelta = DEFAULT_DEDUPE_WINDOW,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._dedupe_window = dedupe_window
        self._now = now

    async def report(self, event: ProviderFailureEvent) -> None:
        """Record one whole-chain failure; never raise into the provider caller."""
        capability = event.capability
        if capability not in _SAFE_CAPABILITIES:
            logger.warning("provider notice dropped: unknown capability")
            return
        operation = _collapse(event.operation, _LABEL_LIMIT) or "unknown"
        error_code = _collapse(event.error_code, _ERROR_CODE_LIMIT) or "provider_error"
        detail = _collapse(event.detail, _DETAIL_LIMIT) or "Provider call failed."
        attempts = [
            {
                "provider": _collapse(attempt.provider, _LABEL_LIMIT) or "unknown",
                "status_code": attempt.status_code,
                "error_code": _collapse(attempt.error_code or "", _ERROR_CODE_LIMIT)
                or None,
                "detail": _collapse(attempt.detail, _ATTEMPT_DETAIL_LIMIT),
            }
            for attempt in event.attempts
        ]
        now = self._now()
        try:
            async with system_session(self._session_factory) as session:
                repository = ProviderErrorNoticeRepository(session)
                existing = await repository.find_recent_unresolved(
                    capability=capability,
                    operation=operation,
                    error_code=error_code,
                    since=now - self._dedupe_window,
                )
                if existing is not None:
                    existing.count += 1
                    existing.last_seen_at = now
                    existing.detail = detail
                    existing.attempts = attempts
                    if event.status_code is not None:
                        existing.status_code = event.status_code
                    await session.flush()
                    return
                await repository.add(
                    ProviderErrorNoticeModel(
                        capability=capability,
                        operation=operation,
                        error_code=error_code,
                        status_code=event.status_code,
                        detail=detail,
                        attempts=attempts,
                        count=1,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
        except Exception:
            # A notice is diagnostics, never the reason a user request fails.
            logger.warning(
                "provider error notice could not be recorded capability=%s operation=%s",
                capability,
                operation,
            )

    async def list_notices(
        self,
        *,
        status: str = "open",
        limit: int = 50,
    ) -> ProviderErrorNoticeListSchema:
        """Return unresolved notices (or all) plus the unresolved count."""
        bounded = max(1, min(limit, 200))
        include_resolved = status == "all"
        async with system_session(self._session_factory) as session:
            repository = ProviderErrorNoticeRepository(session)
            open_count = await repository.count_unresolved()
            rows = await repository.list_notices(
                include_resolved=include_resolved,
                limit=bounded,
            )
            return ProviderErrorNoticeListSchema(
                notices=[_read_notice(row) for row in rows],
                open_count=open_count,
            )

    async def resolve_notice(
        self,
        notice_id: int,
        *,
        user_id: int,
    ) -> ProviderErrorNoticeReadSchema:
        """Mark one notice resolved; a missing id is a domain 404."""
        now = self._now()
        async with system_session(self._session_factory) as session:
            repository = ProviderErrorNoticeRepository(session)
            notice = await repository.get_by_id(notice_id)
            if notice is None:
                raise ProviderNoticeNotFoundError(notice_id)
            await repository.resolve(notice, user_id=user_id, now=now)
            return _read_notice(notice)

    async def resolve_all(self, *, user_id: int) -> ProviderErrorNoticeListSchema:
        """Mark every unresolved notice resolved and return the open list."""
        now = self._now()
        async with system_session(self._session_factory) as session:
            repository = ProviderErrorNoticeRepository(session)
            await repository.resolve_all(user_id=user_id, now=now)
        return await self.list_notices(status="open")


def _read_notice(notice: ProviderErrorNoticeModel) -> ProviderErrorNoticeReadSchema:
    attempts = [
        ProviderAttemptSchema.model_validate(item)
        for item in notice.attempts
        if isinstance(item, dict)
    ]
    return ProviderErrorNoticeReadSchema(
        id=notice.id,
        capability=notice.capability,  # type: ignore[arg-type]
        operation=notice.operation,  # type: ignore[arg-type]
        error_code=notice.error_code,
        status_code=notice.status_code,
        detail=notice.detail,
        attempts=attempts,
        count=notice.count,
        first_seen_at=notice.first_seen_at,
        last_seen_at=notice.last_seen_at,
        resolved_at=notice.resolved_at,
        resolved_by_user_id=notice.resolved_by_user_id,
    )


__all__ = ["DEFAULT_DEDUPE_WINDOW", "ProviderErrorNoticeService"]
