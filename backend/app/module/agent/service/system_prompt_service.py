"""Manage the ordered, global system prompt sections.

The list is read before every conversation is created, so it is cached under the
dedicated global ``system_prompts`` version scope. Writes bump only that scope;
the archive index version stays untouched and archive search caches survive a
prompt edit. Prompt sections are deployment configuration shared by every
account: the cache is deliberately global, and only the root-guarded router may
call the write methods.

Every row is equal. The seeded defaults and root-authored sections share one
table and one CRUD surface; reset simply replaces the collection with the four
seed rows.
"""

import hashlib

from app.module.agent.domain.system_prompt_domain import SystemPromptSection
from app.module.agent.exception.domain_error import (
    AgentInvalidSystemPromptError,
    AgentSystemPromptNotFoundError,
)
from app.module.agent.protocol.system_prompt_cache_protocol import (
    SystemPromptCacheProtocol,
)
from app.module.agent.protocol.system_prompt_repository_protocol import (
    SystemPromptRepositoryProtocol,
)
from app.module.agent.schema.system_prompt_schema import (
    SystemPromptSectionCreateSchema,
    SystemPromptSectionReadSchema,
    SystemPromptSectionUpdateSchema,
)
from app.module.agent.service.system_prompt import default_sections
from app.shared.time import utcnow
from app.shared.types.list_response import ListResponseSchema

SYSTEM_PROMPT_CACHE_SCOPE = "system_prompts"
SYSTEM_PROMPT_CACHE_TTL_SECONDS = 30
# The v2 namespace deliberately invalidates cached lists written before the
# unified table existed. Without it, a deployment could serve a custom-only list
# for up to the 30-second TTL after the migration materialized the defaults.
SYSTEM_PROMPT_CACHE_NAMESPACE = "system_prompts_v2"


def _cache_key(version: int) -> str:
    """Build a versioned cache key without importing another slice's helper.

    The key shape is fixed at ``apsor:<version>:system_prompts_v2:<sha256>``.
    Once the version bumps, the old key is no longer read, so entries do not
    need to be deleted one by one and archive-index or provider-registry scopes
    are not disturbed.
    """
    digest = hashlib.sha256(SYSTEM_PROMPT_CACHE_NAMESPACE.encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{SYSTEM_PROMPT_CACHE_NAMESPACE}:{digest}"


class SystemPromptService:
    """Validate, persist, reorder, reset, and cache prompt sections."""

    def __init__(
        self,
        *,
        repository: SystemPromptRepositoryProtocol,
        cache: SystemPromptCacheProtocol,
        cache_ttl_seconds: int = SYSTEM_PROMPT_CACHE_TTL_SECONDS,
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def list_sections(self) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Return every section in ``sort_order, id`` order, cache first."""
        version = await self.cache.get_version(SYSTEM_PROMPT_CACHE_SCOPE)
        key = _cache_key(version)
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return ListResponseSchema[SystemPromptSectionReadSchema].model_validate(cached)

        rows = await self.repository.list_sections()
        response = _list_schema(rows)
        # The 30-second TTL is a second guard: even if version incrementing
        # fails (for example an external process writes the DB directly), the
        # list returns to the database state shortly.
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response

    async def get_active_sections(self) -> list[SystemPromptSection]:
        """Return every non-empty section in display order.

        Empty bodies are skipped so a directly-edited row can never inject an
        empty provider heading.
        """
        response = await self.list_sections()
        return [
            SystemPromptSection(
                id=item.id,
                title=item.title,
                body=item.body,
                sort_order=item.sort_order,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in sorted(
                response.resources,
                key=lambda item: (item.sort_order, item.id),
            )
            if item.body.strip()
        ]

    async def create_section(
        self,
        payload: SystemPromptSectionCreateSchema,
    ) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Append one section, or honor an explicit ``sort_order``."""
        title, body = _normalize(title=payload.title, body=payload.body)
        sort_order = payload.sort_order
        if sort_order is None:
            sort_order = await self.repository.next_sort_order()
        await self.repository.create_section(
            title=title,
            body=body,
            sort_order=sort_order,
            now=utcnow(),
        )
        return await self._write_result()

    async def update_section(
        self,
        section_id: int,
        payload: SystemPromptSectionUpdateSchema,
    ) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Replace one section; a missing ``sort_order`` keeps its current slot."""
        title, body = _normalize(title=payload.title, body=payload.body)
        existing = await self.repository.get_section(section_id)
        if existing is None:
            raise AgentSystemPromptNotFoundError(section_id)
        sort_order = payload.sort_order
        if sort_order is None:
            sort_order = existing.sort_order
        updated = await self.repository.update_section(
            section_id,
            title=title,
            body=body,
            sort_order=sort_order,
            now=utcnow(),
        )
        if updated is None:
            raise AgentSystemPromptNotFoundError(section_id)
        return await self._write_result()

    async def delete_section(
        self,
        section_id: int,
    ) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Hard-delete one section and return the remaining list."""
        deleted = await self.repository.delete_section(section_id)
        if not deleted:
            raise AgentSystemPromptNotFoundError(section_id)
        return await self._write_result()

    async def reorder_sections(
        self,
        section_ids: list[int],
    ) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Rewrite the complete order; partial or duplicate input is a 422."""
        try:
            await self.repository.reorder_sections(section_ids, now=utcnow())
        except ValueError as exc:
            # The repository only reports the structural set mismatch; translate
            # it into the slice's stable error code so it never becomes a 500.
            raise AgentInvalidSystemPromptError(str(exc)) from exc
        return await self._write_result()

    async def reset_sections(self) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Replace every row with the four seeded defaults.

        Custom sections are removed too, and the defaults receive fresh
        identities. Existing conversations keep their frozen prompt; only new
        conversations see the reset collection.
        """
        await self.repository.replace_with_defaults(
            default_sections(),
            now=utcnow(),
        )
        return await self._write_result()

    async def _write_result(self) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Invalidate the scoped cache, then read the committed rows back.

        The bump only increments the ``system_prompts`` version; it does not
        touch the global index. Reading through ``list_sections`` afterwards
        returns the actual database state (including trimmed fields, identities,
        and adjusted sort orders) instead of a locally assembled copy.
        """
        await self.cache.bump_version(SYSTEM_PROMPT_CACHE_SCOPE)
        return await self.list_sections()


def _normalize(*, title: str, body: str) -> tuple[str, str]:
    """Trim both fields and reject whitespace-only values.

    Pydantic's ``min_length`` alone would turn a whitespace-only value into the
    generic validation envelope. Trimming first and raising
    ``agent_invalid_system_prompt`` lets the browser handle blank and too-short
    values with the same stable error code.
    """
    title = title.strip()
    body = body.strip()
    if not title or not body:
        raise AgentInvalidSystemPromptError("A system prompt title and body are required.")
    return title, body


def _list_schema(
    rows: list[SystemPromptSection],
) -> ListResponseSchema[SystemPromptSectionReadSchema]:
    resources = [SystemPromptSectionReadSchema.model_validate(row) for row in rows]
    return ListResponseSchema[SystemPromptSectionReadSchema](
        total_results=len(resources),
        start_index=1,
        items_per_page=len(resources),
        resources=resources,
    )


__all__ = [
    "SYSTEM_PROMPT_CACHE_SCOPE",
    "SYSTEM_PROMPT_CACHE_TTL_SECONDS",
    "SystemPromptService",
]
