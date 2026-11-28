"""The dedicated worker's life-story loop.

Each cycle settles cancellations, recovers expired leases, and claims at most
one queued job in a maintenance session (ids only). The job then runs in its
owner's RLS session in three short phases so no database transaction is held
open across the model call:

1. **Prepare** (owner session): cancel and idempotency checks, configuration,
   the companion's persona, a bounded selection of the owner's own memories
   and files, a clipped canon digest, the account's own auxiliary model, and
   the chat allowance. Missing pieces end the job as ``skipped`` with a stable
   code.
2. **Write** (no session): one model call with bounded output.
3. **Save** (owner session): cancel check, judge the output, store the story
   as a per-account lore item ``g-<id>``, and stamp the bond.

Logs carry ids and codes only; prompt, memories, and story text never reach
them.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.companion.domain.life_story_domain import (
    FAIL_INTERNAL,
    FAIL_TEMPLATE_INVALID,
    LEASE_SECONDS,
    SKIP_COMPANION_GONE,
    SKIP_DISABLED,
    SKIP_MODEL_NOT_ASSIGNED,
    SKIP_NO_MATERIAL,
    SKIP_QUOTA,
    SYSTEM_REQUIRED_PLACEHOLDERS,
    USER_REQUIRED_PLACEHOLDERS,
    LifeStoryGenerationError,
    LifeStoryRejectedError,
    LifeStoryTemplateError,
    SourceRefs,
    clip_text,
    generated_fragment_key,
    language_name,
    parse_story,
    pending_fragment_key,
    render_prompt,
    retry_delay,
)
from app.module.companion.domain.story_domain import (
    TEMPLATE_LIFE_STORY_SYSTEM,
    TEMPLATE_LIFE_STORY_USER,
    CompanionRuntimeConfig,
)
from app.module.companion.exception.domain_error import CompanionRefNotFoundError
from app.module.companion.protocol.companion_story_protocol import (
    CompanionContentProviderProtocol,
    CompanionStoryConfigProviderProtocol,
)
from app.module.companion.protocol.life_story_protocol import (
    LifeStoryGeneration,
    LifeStoryJobQueueProtocol,
    LifeStoryMaterial,
    LifeStoryMaterialRequest,
    LifeStoryMaterialSelectorProtocol,
    LifeStoryRepositoryProtocol,
    LifeStoryTextGeneratorProtocol,
)
from app.module.companion.service.companion_story_service import CompanionStoryService
from app.module.companion.service.life_story_templates import seed_template
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

MaterialFactory = Callable[[AsyncSession, int], LifeStoryMaterialSelectorProtocol]
GeneratorFactory = Callable[
    [AsyncSession, int, int],
    Awaitable[LifeStoryTextGeneratorProtocol | None],
]
StoryServiceFactory = Callable[[AsyncSession, int], CompanionStoryService]
AllowanceCheck = Callable[[int], Awaitable[bool]]
RepositoryFactory = Callable[[AsyncSession, int], LifeStoryRepositoryProtocol]
QueueFactory = Callable[[AsyncSession], LifeStoryJobQueueProtocol]


@dataclass(frozen=True)
class _Prepared:
    """Everything phase 2 needs; holds no session."""

    job_id: int
    companion_ref: str
    locale: str
    attempts: int
    max_attempts: int
    system: str
    user: str
    max_output_tokens: int
    max_chars: int
    tier: str
    require_review: bool
    banned_terms: tuple[str, ...]
    source_refs: SourceRefs
    template_version: int
    generator: LifeStoryTextGeneratorProtocol


class LifeStoryWorker:
    """Claim and write queued life stories, one at a time."""

    def __init__(
        self,
        *,
        database: Database,
        config: CompanionStoryConfigProviderProtocol,
        content: CompanionContentProviderProtocol,
        story_service: StoryServiceFactory,
        materials: MaterialFactory,
        generator: GeneratorFactory,
        chat_allowed: AllowanceCheck,
        repository: RepositoryFactory,
        queue: QueueFactory,
        lease: timedelta = timedelta(seconds=LEASE_SECONDS),
    ) -> None:
        self.database = database
        self.config = config
        self.content = content
        self.story_service = story_service
        self.materials = materials
        self.generator = generator
        self.chat_allowed = chat_allowed
        self.repository = repository
        self.queue = queue
        self.lease = lease

    # --- loop ----------------------------------------------------------------

    async def _claim(self) -> tuple[int, int, str] | None:
        global_config = await self.config.load(None)
        now = utcnow()
        async with self.database.maintenance_session() as session:
            queue = self.queue(session)
            await queue.settle_cancellations(now)
            await queue.recover_stale(now, max(1, global_config.life_story.max_attempts))
            return await queue.claim(now, self.lease)

    async def run_once(self) -> int:
        """Process at most one due job; return how many stories were written."""
        claimed = await self._claim()
        if claimed is None:
            return 0
        job_id, user_id, role = claimed
        try:
            return 1 if await self.process(job_id, user_id, role) else 0
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("life story job crashed job_id=%s user_id=%s", job_id, user_id)
            await self._finish(job_id, user_id, role, status="failed", error=FAIL_INTERNAL)
            return 0

    async def drain(self, max_jobs: int = 100) -> int:
        """Process due jobs until none is left (bounded by ``max_jobs``)."""
        written = 0
        for _ in range(max(1, max_jobs)):
            claimed = await self._claim()
            if claimed is None:
                break
            job_id, user_id, role = claimed
            try:
                if await self.process(job_id, user_id, role):
                    written += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("life story job crashed job_id=%s user_id=%s", job_id, user_id)
                await self._finish(job_id, user_id, role, status="failed", error=FAIL_INTERNAL)
        return written

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Poll for jobs until ``stop_event`` is set."""
        logger.info("life story worker started")
        while stop_event is None or not stop_event.is_set():
            written = 0
            poll_seconds = 30
            try:
                poll_seconds = max(5, (await self.config.load(None)).life_story.poll_seconds)
                written = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("life story worker cycle failed")
            if written:
                await asyncio.sleep(0)
                continue
            if stop_event is None:
                await asyncio.sleep(poll_seconds)
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass

    # --- one job -------------------------------------------------------------

    async def process(self, job_id: int, user_id: int, role: str) -> bool:
        """Run one claimed job through prepare, write, and save."""
        prepared = await self._prepare(job_id, user_id, role)
        if prepared is None:
            return False
        try:
            generation = await prepared.generator.generate(
                system=prepared.system,
                messages=[{"role": "user", "content": prepared.user}],
                max_output_tokens=prepared.max_output_tokens,
            )
        except LifeStoryGenerationError as exc:
            await self._settle_failure(
                prepared,
                user_id,
                role,
                code=exc.code,
                retryable=exc.retryable,
                skip=exc.skip,
            )
            return False
        return await self._save(prepared, user_id, role, generation)

    async def _prepare(self, job_id: int, user_id: int, role: str) -> _Prepared | None:
        async with self.database.user_session(user_id, role) as session:
            repository = self.repository(session, user_id)
            job = await repository.get_job(job_id)
            if job is None:
                return None
            now = utcnow()
            if job.status == "cancel_requested":
                await repository.finish_job(job_id, status="cancelled", now=now)
                return None
            if job.status != "running":
                return None
            if await repository.story_for_job(job_id) is not None:
                await repository.finish_job(job_id, status="succeeded", now=now)
                return None
            config = await self.config.load(user_id)
            life = config.life_story

            async def skip(code: str) -> None:
                await repository.finish_job(job_id, status="skipped", now=now, skip_reason=code)
                logger.info("life story skipped job_id=%s reason=%s", job_id, code)

            if job.trigger == "cadence" and not life.enabled:
                await skip(SKIP_DISABLED)
                return None
            stories = self.story_service(session, user_id)
            try:
                target = await stories.resolve(job.companion_ref)
            except CompanionRefNotFoundError:
                await skip(SKIP_COMPANION_GONE)
                return None
            persona, _ = await stories.persona(target, job.locale)
            used_memories, used_files = await repository.used_source_ids()
            themes = tuple(
                dict.fromkeys(
                    theme
                    for fragment in await stories.fragments(target, job.locale)
                    for theme in fragment.themes
                )
            )[:4]
            materials = await self.materials(session, user_id).select(
                LifeStoryMaterialRequest(
                    limit=max(1, life.memory_limit),
                    max_chars=max(200, life.memory_chars),
                    seed_themes=themes,
                    exclude_memory_ids=used_memories,
                    exclude_file_ids=used_files,
                )
            )
            if not materials:
                await skip(SKIP_NO_MATERIAL)
                return None
            generator = await self.generator(session, user_id, max(64, life.max_output_tokens))
            if generator is None:
                await skip(SKIP_MODEL_NOT_ASSIGNED)
                return None
            if not await self.chat_allowed(user_id):
                await skip(SKIP_QUOTA)
                return None
            canon = await self._canon_digest(target.preset_id, job.locale, life.canon_chars)
            try:
                system, user = self._render(
                    config,
                    companion_name=target.name,
                    persona=persona,
                    canon=canon,
                    materials=materials,
                    locale=job.locale,
                    max_chars=life.max_chars,
                )
            except LifeStoryTemplateError:
                await repository.finish_job(
                    job_id,
                    status="failed",
                    now=now,
                    error_code=FAIL_TEMPLATE_INVALID,
                )
                logger.warning("life story template invalid job_id=%s", job_id)
                return None
            return _Prepared(
                job_id=job_id,
                companion_ref=job.companion_ref,
                locale=job.locale,
                attempts=job.attempts,
                max_attempts=max(1, life.max_attempts),
                system=system,
                user=user,
                max_output_tokens=max(64, life.max_output_tokens),
                max_chars=life.max_chars,
                tier=life.tier,
                require_review=life.require_review,
                banned_terms=config.banned_address_terms,
                source_refs=SourceRefs(
                    memory_ids=tuple(m.source_id for m in materials if m.kind == "memory"),
                    file_ids=tuple(m.source_id for m in materials if m.kind == "file"),
                ),
                template_version=config.version,
                generator=generator,
            )

    async def _save(
        self,
        prepared: _Prepared,
        user_id: int,
        role: str,
        generation: LifeStoryGeneration,
    ) -> bool:
        async with self.database.user_session(user_id, role) as session:
            repository = self.repository(session, user_id)
            now = utcnow()
            status = await repository.job_status(prepared.job_id)
            if status == "cancel_requested":
                await repository.finish_job(prepared.job_id, status="cancelled", now=now)
                logger.info("life story cancelled after writing job_id=%s", prepared.job_id)
                return False
            if status != "running":
                return False
            try:
                story = parse_story(
                    generation.text,
                    max_chars=prepared.max_chars,
                    banned_terms=prepared.banned_terms,
                )
            except LifeStoryRejectedError as exc:
                await self._retry_or_fail(repository, prepared, code=exc.code)
                return False
            row = await repository.add_story(
                {
                    "companion_ref": prepared.companion_ref,
                    "locale": prepared.locale,
                    "fragment_key": pending_fragment_key(prepared.job_id),
                    "title": story.title,
                    "text": story.text,
                    "tier": prepared.tier,
                    "themes": [],
                    "status": "draft" if prepared.require_review else "published",
                    "source_refs": prepared.source_refs.as_json(),
                    "job_id": prepared.job_id,
                    "model": generation.model,
                    "provider_config_id": generation.provider_config_id,
                    "prompt_tokens": generation.prompt_tokens,
                    "completion_tokens": generation.completion_tokens,
                    "template_version": prepared.template_version,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if row is not None:
                await repository.set_fragment_key(row, generated_fragment_key(row.id))
                await repository.mark_life_story(prepared.companion_ref, now)
            await repository.finish_job(prepared.job_id, status="succeeded", now=now)
            logger.info(
                "life story written job_id=%s user_id=%s story_id=%s",
                prepared.job_id,
                user_id,
                row.id if row is not None else None,
            )
            return row is not None

    async def _settle_failure(
        self,
        prepared: _Prepared,
        user_id: int,
        role: str,
        *,
        code: str,
        retryable: bool,
        skip: bool,
    ) -> None:
        async with self.database.user_session(user_id, role) as session:
            repository = self.repository(session, user_id)
            now = utcnow()
            if await repository.job_status(prepared.job_id) != "running":
                return
            if skip:
                await repository.finish_job(
                    prepared.job_id,
                    status="skipped",
                    now=now,
                    skip_reason=code,
                )
                logger.info("life story skipped job_id=%s reason=%s", prepared.job_id, code)
                return
            if retryable:
                await self._retry_or_fail(repository, prepared, code=code)
                return
            await repository.finish_job(prepared.job_id, status="failed", now=now, error_code=code)
            logger.warning("life story failed job_id=%s code=%s", prepared.job_id, code)

    async def _retry_or_fail(
        self,
        repository: LifeStoryRepositoryProtocol,
        prepared: _Prepared,
        *,
        code: str,
    ) -> None:
        now = utcnow()
        if prepared.attempts < prepared.max_attempts:
            await repository.requeue_job(
                prepared.job_id,
                not_before=now + retry_delay(prepared.attempts),
                error_code=code,
            )
            logger.info(
                "life story requeued job_id=%s code=%s attempt=%s",
                prepared.job_id,
                code,
                prepared.attempts,
            )
            return
        await repository.finish_job(prepared.job_id, status="failed", now=now, error_code=code)
        logger.warning("life story failed job_id=%s code=%s", prepared.job_id, code)

    async def _finish(
        self,
        job_id: int,
        user_id: int,
        role: str,
        *,
        status: str,
        error: str,
    ) -> None:
        try:
            async with self.database.user_session(user_id, role) as session:
                repository = self.repository(session, user_id)
                if await repository.job_status(job_id) in {"running", "cancel_requested"}:
                    await repository.finish_job(
                        job_id,
                        status=status,
                        now=utcnow(),
                        error_code=error,
                    )
        except Exception:
            logger.exception("life story job could not be closed job_id=%s", job_id)

    # --- prompt material -----------------------------------------------------

    async def _canon_digest(self, preset_id: str | None, locale: str, max_chars: int) -> str:
        keys = [f"character:{preset_id}"] if preset_id else []
        keys += ["world", "glossary"]
        parts: list[str] = []
        budget = max(200, max_chars)
        for key in keys:
            doc = await self.content.world_doc(key, locale)
            if doc is None or not doc.body_md.strip():
                continue
            remaining = budget - sum(len(part) for part in parts)
            if remaining <= 0:
                break
            parts.append(clip_text(doc.body_md, remaining))
        return "\n\n".join(parts)

    def _render(
        self,
        config: CompanionRuntimeConfig,
        *,
        companion_name: str,
        persona: str,
        canon: str,
        materials: list[LifeStoryMaterial],
        locale: str,
        max_chars: int,
    ) -> tuple[str, str]:
        memories = "\n".join(
            f"- ({item.kind}) {item.title}: {item.excerpt}"
            if item.title
            else f"- ({item.kind}) {item.excerpt}"
            for item in materials
        )
        values = {
            "companion_name": companion_name,
            "persona": persona,
            "canon": canon,
            "memories": memories,
            "language": language_name(locale),
            "max_chars": max_chars,
        }
        system_template = config.template(TEMPLATE_LIFE_STORY_SYSTEM) or seed_template(
            TEMPLATE_LIFE_STORY_SYSTEM
        )
        user_template = config.template(TEMPLATE_LIFE_STORY_USER) or seed_template(
            TEMPLATE_LIFE_STORY_USER
        )
        return (
            render_prompt(system_template, values, SYSTEM_REQUIRED_PLACEHOLDERS),
            render_prompt(user_template, values, USER_REQUIRED_PLACEHOLDERS),
        )


__all__ = ["LifeStoryWorker"]
