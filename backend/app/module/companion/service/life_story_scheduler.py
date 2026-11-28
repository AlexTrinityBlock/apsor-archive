"""Queue a life story every few conversations with a companion.

Runs on the agent's owner session right after a run is counted toward the
bond. Enqueueing is a single idempotent insert keyed by
``cadence:<ref>:<conversations>``; nothing here calls a provider, so a
completed answer never waits on story writing.
"""

import logging

from app.module.companion.domain.life_story_domain import (
    cadence_trigger_key,
    life_story_due,
    window_start,
)
from app.module.companion.protocol.companion_story_protocol import (
    CompanionStoryConfigProviderProtocol,
)
from app.module.companion.protocol.life_story_protocol import LifeStoryRepositoryProtocol
from app.shared.time import utcnow

logger = logging.getLogger(__name__)


class LifeStoryScheduler:
    """Count conversations per companion and queue cadence life stories."""

    def __init__(
        self,
        *,
        repository: LifeStoryRepositoryProtocol,
        config: CompanionStoryConfigProviderProtocol,
        user_id: int,
    ) -> None:
        self.repository = repository
        self.config = config
        self.user_id = user_id

    async def record_conversation(
        self,
        companion_ref: str,
        locale: str,
        conversation_id: int,
    ) -> int | None:
        """Count the conversation once, then queue a story when one is due.

        Returns the new job id, or ``None`` when nothing was queued.
        """
        now = utcnow()
        counters = await self.repository.record_conversation(companion_ref, conversation_id, now)
        if counters is None:
            return None
        conversations, last_life_story = counters
        return await self.maybe_enqueue(
            companion_ref,
            locale,
            conversations=conversations,
            last_life_story_conversations=last_life_story,
        )

    async def maybe_enqueue(
        self,
        companion_ref: str,
        locale: str,
        *,
        conversations: int,
        last_life_story_conversations: int,
    ) -> int | None:
        """Queue one cadence job when the schedule, cap, and queue allow it."""
        config = (await self.config.load(self.user_id)).life_story
        if not config.enabled:
            return None
        if conversations - last_life_story_conversations < max(1, config.every_conversations):
            return None
        now = utcnow()
        due = life_story_due(
            enabled=config.enabled,
            conversations=conversations,
            last_life_story_conversations=last_life_story_conversations,
            every_conversations=config.every_conversations,
            stories_last_30d=await self.repository.count_recent(window_start(now)),
            max_per_30d=config.max_per_30d,
            has_active_job=await self.repository.has_active_job(),
        )
        if not due:
            return None
        job_id = await self.repository.enqueue(
            companion_ref=companion_ref,
            locale=locale,
            trigger="cadence",
            trigger_key=cadence_trigger_key(companion_ref, conversations),
            now=now,
        )
        if job_id is not None:
            logger.info(
                "life story queued user_id=%s job_id=%s conversations=%s",
                self.user_id,
                job_id,
                conversations,
            )
        return job_id


__all__ = ["LifeStoryScheduler"]
