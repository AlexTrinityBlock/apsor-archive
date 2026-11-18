"""Background text generation that consumes the account's chat allowance.

Agent-run usage already reaches ``app_user.total_tokens`` through the
``agent_run`` trigger. Summary, memory-title, document-analysis, and other
knowledge-side provider calls bypass that trigger, so this wrapper checks the
same chat allowance before each call and records the provider's usage after a
successful one. It must never be used for the agent's own generator.
"""

import logging
from collections.abc import Mapping

from app.module.knowledge.exception.domain_error import ChatUsageLimitExceededError
from app.module.knowledge.protocol.chat_usage_quota_protocol import (
    ChatUsageQuotaProtocol,
)
from app.module.knowledge.protocol.text_generator_protocol import (
    AiCompletion,
    TextGeneratorProtocol,
)

logger = logging.getLogger(__name__)


class MeteredTextGenerator:
    """A ``TextGeneratorProtocol`` decorator with chat-allowance accounting."""

    def __init__(
        self,
        inner: TextGeneratorProtocol,
        quota: ChatUsageQuotaProtocol | None = None,
    ) -> None:
        self._inner = inner
        self._quota = quota

    @property
    def configured(self) -> bool:
        return self._inner.configured

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def _ensure_allowed(self) -> None:
        if self._quota is not None and not await self._quota.chat_allowed():
            raise ChatUsageLimitExceededError()

    async def _record(self, usage: Mapping[str, int]) -> None:
        if self._quota is None:
            return
        if not usage:
            logger.debug("Background chat call returned no usage; nothing recorded")
            return
        try:
            await self._quota.record_chat_usage(usage)
        except Exception:
            # Accounting must never turn a successful summary, title, or
            # extraction into a user-visible failure.
            logger.warning(
                "Background chat usage could not be recorded",
                exc_info=True,
            )

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        await self._ensure_allowed()
        completion = await self._inner.complete_text(system_prompt, user_prompt)
        await self._record(completion.usage)
        return completion

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        await self._ensure_allowed()
        completion = await self._inner.complete_json(system_prompt, user_prompt)
        await self._record(completion.usage)
        return completion


__all__ = ["MeteredTextGenerator"]
