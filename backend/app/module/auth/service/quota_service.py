"""Consumer-facing enforcement for one account's usage allowances.

The service is bound to the authenticated account when the composition root
builds it. Every operation opens its own short ``system_session``: ``app_user``
is deliberately outside row-level security because login and session lookup run
before an owner context exists, and the captured row is the only one touched.
No provider call ever runs while a session is open.

The admin projections live in :mod:`app.module.auth.service.account_service`;
this service only answers allow/deny questions and records lifetime counters.
"""

import logging
from collections.abc import Mapping

from sqlalchemy import select, update

from app.infrastructure.database.session import Database
from app.module.auth.domain.quota_domain import (
    QUOTA_FIELDS,
    QuotaCategory,
    quota_allows,
    quota_chat_allowed,
)
from app.module.auth.model.auth_model import AppUserModel

logger = logging.getLogger(__name__)


def _usage_int(usage: Mapping[str, int], key: str) -> int:
    """Read one non-negative provider counter without trusting its type."""
    try:
        return max(0, int(usage.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


class AccountQuotaService:
    """Read and update the five captured account's usage allowance.

    The class structurally implements the consumer protocols defined by the
    agent, knowledge, and web-research slices; it never imports their code.
    """

    def __init__(self, database: Database, user_id: int) -> None:
        self.database = database
        self.user_id = user_id

    async def _load(self) -> AppUserModel | None:
        async with self.database.system_session() as session:
            statement = select(AppUserModel).where(AppUserModel.id == self.user_id)
            return (await session.execute(statement)).scalar_one_or_none()

    async def _allowed(self, category: QuotaCategory, units: int = 0) -> bool:
        row = await self._load()
        if row is None:
            logger.warning(
                "Usage quota check skipped user_id=%s category=%s reason=missing_row",
                self.user_id,
                category,
            )
            return False
        if category == "chat":
            return quota_chat_allowed(row)
        return quota_allows(row, category, units)

    async def chat_allowed(self) -> bool:
        """Return whether the account may start another chat step."""
        return await self._allowed("chat")

    async def embedding_allowed(self, characters: int) -> bool:
        """Return whether one embedding batch of ``characters`` fits."""
        return await self._allowed("embedding", characters)

    async def record_embedding(self, characters: int) -> None:
        """Add ``characters`` to the embedding lifetime counter; best effort."""
        await self._record("embedding", characters)

    async def record_chat_usage(self, usage: Mapping[str, int]) -> None:
        """Fold one background provider call into the chat lifetime counters.

        Agent-run usage remains trigger-owned. This path deliberately does not
        touch ``agent_turns`` or ``last_agent_activity_at``; it only consumes the
        same ``total_tokens`` allowance that the trigger maintains. Best effort:
        a failed update never fails the provider call.
        """
        if not usage:
            return
        prompt_tokens = _usage_int(usage, "prompt_tokens")
        completion_tokens = _usage_int(usage, "completion_tokens")
        total_tokens = _usage_int(usage, "total_tokens")
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        cached_tokens = _usage_int(usage, "prompt_cache_hit_tokens")
        if cached_tokens == 0:
            cached_tokens = _usage_int(usage, "cached_tokens")
        if not any((prompt_tokens, completion_tokens, total_tokens, cached_tokens)):
            return
        try:
            async with self.database.system_session() as session:
                result = await session.execute(
                    update(AppUserModel)
                    .where(AppUserModel.id == self.user_id)
                    .values(
                        {
                            AppUserModel.prompt_tokens.key: (
                                AppUserModel.prompt_tokens + prompt_tokens
                            ),
                            AppUserModel.completion_tokens.key: (
                                AppUserModel.completion_tokens + completion_tokens
                            ),
                            AppUserModel.total_tokens.key: (
                                AppUserModel.total_tokens + total_tokens
                            ),
                            AppUserModel.cached_tokens.key: (
                                AppUserModel.cached_tokens + cached_tokens
                            ),
                            AppUserModel.api_calls.key: AppUserModel.api_calls + 1,
                        }
                    )
                )
                updated = int(getattr(result, "rowcount", 0) or 0)
                if updated == 0:
                    logger.warning(
                        "Chat usage record skipped user_id=%s reason=missing_row",
                        self.user_id,
                    )
        except Exception:
            logger.warning(
                "Chat usage record failed user_id=%s",
                self.user_id,
                exc_info=True,
            )

    async def web_search_allowed(self) -> bool:
        """Return whether the account may make one web search provider call."""
        return await self._allowed("web_search", 1)

    async def record_web_search(self) -> None:
        """Add one call to the web-search lifetime counter; best effort."""
        await self._record("web_search", 1)

    async def web_fetch_allowed(self) -> bool:
        """Return whether the account may make one web fetch provider call."""
        return await self._allowed("web_fetch", 1)

    async def record_web_fetch(self) -> None:
        """Add one call to the web-fetch lifetime counter; best effort."""
        await self._record("web_fetch", 1)

    async def _record(self, category: QuotaCategory, units: int) -> None:
        if units <= 0:
            return
        field = getattr(AppUserModel, QUOTA_FIELDS[category].lifetime)
        try:
            async with self.database.system_session() as session:
                result = await session.execute(
                    update(AppUserModel)
                    .where(AppUserModel.id == self.user_id)
                    .values({field.key: field + units})
                )
                updated = int(getattr(result, "rowcount", 0) or 0)
                if updated == 0:
                    logger.warning(
                        "Usage quota record skipped user_id=%s category=%s "
                        "reason=missing_row",
                        self.user_id,
                        category,
                    )
        except Exception:
            # Usage accounting must never turn a successful provider call into
            # a user-visible failure. The next check still fails closed if the
            # counter could not be written.
            logger.warning(
                "Usage quota record failed user_id=%s category=%s units=%d",
                self.user_id,
                category,
                units,
                exc_info=True,
            )


__all__ = ["AccountQuotaService"]
