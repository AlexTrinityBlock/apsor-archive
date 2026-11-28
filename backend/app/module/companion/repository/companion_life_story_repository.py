"""Persistence for life-story jobs, generated stories, and their bond counters.

Two kinds of session use this module:

- :class:`LifeStoryRepository` runs in the owner's RLS session and filters by
  ``user_id`` explicitly as well.
- :class:`LifeStoryJobQueue` runs in the worker's maintenance session. It only
  claims, recovers, and finishes jobs by id; it never reads story text or the
  archive, and every job is then processed in its owner's session.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.companion.model.companion_life_story_model import (
    CompanionGeneratedStoryModel,
    CompanionStoryJobModel,
)
from app.module.companion.model.companion_story_model import CompanionBondModel


class LifeStoryRepository:
    """Owner-scoped reads and writes for one account's life stories."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    # --- bond counters -----------------------------------------------------

    async def record_conversation(
        self,
        companion_ref: str,
        conversation_id: int,
        now: datetime,
    ) -> tuple[int, int] | None:
        """Count ``conversation_id`` once toward the bond's conversations.

        Conversation ids only increase, so a run in a newer conversation counts
        and a return to an older one does not. Returns the bond's
        ``(conversations, last_life_story_conversations)`` after the update, or
        ``None`` when no bond row exists yet.
        """
        await self.session.execute(
            update(CompanionBondModel)
            .where(
                CompanionBondModel.user_id == self.user_id,
                CompanionBondModel.companion_ref == companion_ref,
                (
                    CompanionBondModel.last_conversation_id.is_(None)
                    | (CompanionBondModel.last_conversation_id < conversation_id)
                ),
            )
            .values(
                conversations=CompanionBondModel.conversations + 1,
                last_conversation_id=conversation_id,
                updated_at=now,
            )
        )
        row = (
            await self.session.execute(
                select(
                    CompanionBondModel.conversations,
                    CompanionBondModel.last_life_story_conversations,
                ).where(
                    CompanionBondModel.user_id == self.user_id,
                    CompanionBondModel.companion_ref == companion_ref,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return int(row[0]), int(row[1])

    async def mark_life_story(self, companion_ref: str, now: datetime) -> None:
        """Remember the conversation count at which a life story was written."""
        await self.session.execute(
            update(CompanionBondModel)
            .where(
                CompanionBondModel.user_id == self.user_id,
                CompanionBondModel.companion_ref == companion_ref,
            )
            .values(
                last_life_story_conversations=CompanionBondModel.conversations,
                updated_at=now,
            )
        )

    # --- jobs --------------------------------------------------------------

    async def has_active_job(self) -> bool:
        """Return whether any life-story job of this account is in flight."""
        statement = select(func.count()).where(
            CompanionStoryJobModel.user_id == self.user_id,
            CompanionStoryJobModel.status.in_(("queued", "running", "cancel_requested")),
        )
        return int((await self.session.execute(statement)).scalar_one()) > 0

    async def count_recent(self, since: datetime) -> int:
        """Count jobs that produced or may still produce a story since ``since``."""
        statement = select(func.count()).where(
            CompanionStoryJobModel.user_id == self.user_id,
            CompanionStoryJobModel.created_at >= since,
            CompanionStoryJobModel.status.in_(
                ("queued", "running", "cancel_requested", "succeeded")
            ),
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def enqueue(
        self,
        *,
        companion_ref: str,
        locale: str,
        trigger: str,
        trigger_key: str,
        now: datetime,
        replaces_story_id: int | None = None,
    ) -> int | None:
        """Queue one job; a repeated ``trigger_key`` is a silent no-op."""
        statement = (
            insert(CompanionStoryJobModel)
            .values(
                user_id=self.user_id,
                companion_ref=companion_ref,
                locale=locale,
                trigger=trigger,
                trigger_key=trigger_key,
                replaces_story_id=replaces_story_id,
                status="queued",
                attempts=0,
                not_before=now,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "trigger_key"])
            .returning(CompanionStoryJobModel.id)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_job(self, job_id: int) -> CompanionStoryJobModel | None:
        """Return one of this account's jobs."""
        statement = select(CompanionStoryJobModel).where(
            CompanionStoryJobModel.id == job_id,
            CompanionStoryJobModel.user_id == self.user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def job_status(self, job_id: int) -> str | None:
        """Read the job's status afresh (a cancel may have been committed)."""
        statement = select(CompanionStoryJobModel.status).where(
            CompanionStoryJobModel.id == job_id,
            CompanionStoryJobModel.user_id == self.user_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def finish_job(
        self,
        job_id: int,
        *,
        status: str,
        now: datetime,
        skip_reason: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Move a job to a terminal status and release its lease."""
        await self.session.execute(
            update(CompanionStoryJobModel)
            .where(
                CompanionStoryJobModel.id == job_id,
                CompanionStoryJobModel.user_id == self.user_id,
            )
            .values(
                status=status,
                skip_reason=skip_reason,
                error_code=error_code,
                lease_until=None,
                finished_at=now,
            )
        )

    async def requeue_job(self, job_id: int, *, not_before: datetime, error_code: str) -> None:
        """Put a job back in the queue after a retryable failure."""
        await self.session.execute(
            update(CompanionStoryJobModel)
            .where(
                CompanionStoryJobModel.id == job_id,
                CompanionStoryJobModel.user_id == self.user_id,
                CompanionStoryJobModel.status == "running",
            )
            .values(
                status="queued",
                lease_until=None,
                not_before=not_before,
                error_code=error_code,
            )
        )

    # --- generated stories -------------------------------------------------

    async def story_for_job(self, job_id: int) -> CompanionGeneratedStoryModel | None:
        """Return the story a job already produced (idempotent retry)."""
        statement = select(CompanionGeneratedStoryModel).where(
            CompanionGeneratedStoryModel.user_id == self.user_id,
            CompanionGeneratedStoryModel.job_id == job_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add_story(self, values: dict[str, Any]) -> CompanionGeneratedStoryModel | None:
        """Insert a story; ``None`` when this job's story already exists."""
        statement = (
            insert(CompanionGeneratedStoryModel)
            .values(user_id=self.user_id, **values)
            .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
            .returning(CompanionGeneratedStoryModel.id)
        )
        story_id = (await self.session.execute(statement)).scalar_one_or_none()
        if story_id is None:
            return None
        return await self.session.get(CompanionGeneratedStoryModel, story_id)

    async def set_fragment_key(self, story: CompanionGeneratedStoryModel, key: str) -> None:
        """Give a freshly inserted story its final ``g-<id>`` lore key."""
        story.fragment_key = key
        await self.session.flush()

    async def list_published(
        self,
        companion_ref: str,
        locale: str,
    ) -> list[CompanionGeneratedStoryModel]:
        """Return published stories for one companion and locale, oldest first."""
        statement = (
            select(CompanionGeneratedStoryModel)
            .where(
                CompanionGeneratedStoryModel.user_id == self.user_id,
                CompanionGeneratedStoryModel.companion_ref == companion_ref,
                CompanionGeneratedStoryModel.locale == locale,
                CompanionGeneratedStoryModel.status == "published",
            )
            .order_by(CompanionGeneratedStoryModel.id)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def used_source_ids(self) -> tuple[frozenset[int], frozenset[int]]:
        """Return memory and file ids earlier stories already drew on."""
        statement = select(CompanionGeneratedStoryModel.source_refs).where(
            CompanionGeneratedStoryModel.user_id == self.user_id,
            CompanionGeneratedStoryModel.status != "retired",
        )
        memory_ids: set[int] = set()
        file_ids: set[int] = set()
        for refs in (await self.session.execute(statement)).scalars():
            if not isinstance(refs, dict):
                continue
            memory_ids.update(int(item) for item in refs.get("memory_ids", []) or [])
            file_ids.update(int(item) for item in refs.get("file_ids", []) or [])
        return frozenset(memory_ids), frozenset(file_ids)


class LifeStoryJobQueue:
    """Cross-account claim and recovery, for the worker's maintenance session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def settle_cancellations(self, now: datetime) -> int:
        """Cancel requested jobs that no worker holds."""
        result = await self.session.execute(
            text(
                """
                UPDATE companion_story_job
                SET status = 'cancelled', lease_until = NULL, finished_at = :now
                WHERE status = 'cancel_requested'
                  AND (lease_until IS NULL OR lease_until < :now)
                """
            ),
            {"now": now},
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def recover_stale(self, now: datetime, max_attempts: int) -> int:
        """Requeue expired leases below ``max_attempts``; fail the rest."""
        requeued = await self.session.execute(
            text(
                """
                UPDATE companion_story_job
                SET status = 'queued', lease_until = NULL
                WHERE status = 'running' AND lease_until < :now AND attempts < :max_attempts
                """
            ),
            {"now": now, "max_attempts": max_attempts},
        )
        await self.session.execute(
            text(
                """
                UPDATE companion_story_job
                SET status = 'failed', lease_until = NULL, error_code = 'lease_expired',
                    finished_at = :now
                WHERE status = 'running' AND lease_until < :now AND attempts >= :max_attempts
                """
            ),
            {"now": now, "max_attempts": max_attempts},
        )
        return int(getattr(requeued, "rowcount", 0) or 0)

    async def claim(self, now: datetime, lease: timedelta) -> tuple[int, int, str] | None:
        """Lease the oldest due job; return ``(job_id, user_id, role)``."""
        row = (
            await self.session.execute(
                text(
                    """
                    UPDATE companion_story_job
                    SET status = 'running', lease_until = :lease_until,
                        attempts = attempts + 1
                    WHERE id IN (
                        SELECT id FROM companion_story_job
                        WHERE status = 'queued' AND not_before <= :now
                        ORDER BY not_before, id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING id, user_id
                    """
                ),
                {"now": now, "lease_until": now + lease},
            )
        ).one_or_none()
        if row is None:
            return None
        job_id, user_id = int(row[0]), int(row[1])
        role = (
            await self.session.execute(
                text("SELECT role FROM app_user WHERE id = :user_id"),
                {"user_id": user_id},
            )
        ).scalar_one_or_none()
        return job_id, user_id, str(role or "user")


__all__ = ["LifeStoryJobQueue", "LifeStoryRepository"]
