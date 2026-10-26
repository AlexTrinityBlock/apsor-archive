"""Editable frequently used prompts shown on the empty chat page.

Every prompt belongs to one account. The list is tiny (at most 20 rows per
owner) but read on every new chat, so it is cached under a per-user ``prompts``
version scope. Writes bump only the acting user's scope: the global index
version is reserved for archive content and embeddings.
"""

from app.module.prompt.exception.domain_error import (
    FrequentPromptNotFoundError,
    InvalidFrequentPromptError,
    TooManyFrequentPromptsError,
)
from app.module.prompt.model.frequent_prompt_model import FrequentlyUsedPromptModel
from app.module.prompt.protocol.frequent_prompt_cache_protocol import (
    FrequentPromptCacheProtocol,
)
from app.module.prompt.protocol.frequent_prompt_repository_protocol import (
    FrequentlyUsedPromptRepositoryProtocol,
)
from app.module.prompt.schema.frequent_prompt_schema import (
    FrequentlyUsedPromptCreateSchema,
    FrequentlyUsedPromptReadSchema,
    FrequentlyUsedPromptUpdateSchema,
)
from app.module.prompt.service.frequent_prompt_cache_key import (
    frequent_prompt_cache_key,
    frequent_prompt_version_scope,
)
from app.shared.time import utcnow
from app.shared.types.list_response import ListResponseSchema

MAX_FREQUENT_PROMPTS = 20
FREQUENT_PROMPT_CACHE_TTL_SECONDS = 60
PROMPT_CACHE_SCOPE = "prompts"
PROMPT_CACHE_NAMESPACE = "frequent_prompts"

PromptPayload = FrequentlyUsedPromptCreateSchema | FrequentlyUsedPromptUpdateSchema


class FrequentlyUsedPromptService:
    """Validate, persist, and cache one owner's prompt shortcuts."""

    def __init__(
        self,
        *,
        repository: FrequentlyUsedPromptRepositoryProtocol,
        cache: FrequentPromptCacheProtocol,
        cache_ttl_seconds: int = FREQUENT_PROMPT_CACHE_TTL_SECONDS,
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def list_prompts(
        self,
        user_id: int,
    ) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
        """Return one owner's prompts in ``sort_order, id`` order.

        The cache key combines the per-user version with the acting user id, so
        another account can never read this snapshot. A write bumps the version
        instead of deleting entries; the old key simply stops being requested
        and expires after the TTL.
        """
        version = await self.cache.get_version(self._version_scope(user_id))
        key = frequent_prompt_cache_key(version, PROMPT_CACHE_NAMESPACE, user_id)
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return ListResponseSchema[FrequentlyUsedPromptReadSchema].model_validate(cached)

        rows = await self.repository.list_for_user(user_id)
        response = _list_schema(rows)
        # The 60-second TTL still returns the list to the database state even if
        # the version bump mechanism fails.
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response

    async def create_prompt(
        self,
        user_id: int,
        payload: FrequentlyUsedPromptCreateSchema,
    ) -> FrequentlyUsedPromptReadSchema:
        title, prompt_text = _normalize(payload)
        # The 20-row cap is a per-owner business rule, not a database
        # constraint; count and insert in the same transaction so callers
        # outside the UI cannot grow one archive without bound.
        count = await self.repository.count_for_user(user_id)
        if count >= MAX_FREQUENT_PROMPTS:
            raise TooManyFrequentPromptsError(MAX_FREQUENT_PROMPTS)

        row = await self.repository.add(
            user_id=user_id,
            title=title,
            prompt_text=prompt_text,
            sort_order=payload.sort_order,
            now=utcnow(),
        )
        # Invalidate only the acting user's prompt scope so the next GET
        # rebuilds the snapshot.
        await self._invalidate(user_id)
        return FrequentlyUsedPromptReadSchema.model_validate(row)

    async def update_prompt(
        self,
        user_id: int,
        prompt_id: int,
        payload: FrequentlyUsedPromptUpdateSchema,
    ) -> FrequentlyUsedPromptReadSchema:
        title, prompt_text = _normalize(payload)
        row = await self.repository.update(
            user_id,
            prompt_id,
            title=title,
            prompt_text=prompt_text,
            sort_order=payload.sort_order,
            now=utcnow(),
        )
        if row is None:
            raise FrequentPromptNotFoundError(prompt_id)

        await self._invalidate(user_id)
        return FrequentlyUsedPromptReadSchema.model_validate(row)

    async def reorder_prompts(
        self,
        user_id: int,
        prompt_ids: list[int],
    ) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
        """Replace one owner's complete shortcut order atomically.

        Missing, duplicate, or unknown ids all mean the order is inconsistent.
        The repository reports the set mismatch and this layer maps it to the
        stable ``invalid_frequent_prompt`` error instead of a 500. The response
        is the freshly flushed database order; the version bump makes the next
        GET rebuild the cached snapshot.
        """
        try:
            rows = await self.repository.reorder(user_id, prompt_ids, now=utcnow())
        except ValueError as exc:
            raise InvalidFrequentPromptError(str(exc)) from exc

        await self._invalidate(user_id)
        return _list_schema(rows)

    async def delete_prompt(self, user_id: int, prompt_id: int) -> None:
        """Hard-delete one prompt; the identity sequence is never rewound."""
        deleted = await self.repository.delete(user_id, prompt_id)
        if not deleted:
            raise FrequentPromptNotFoundError(prompt_id)

        await self._invalidate(user_id)

    def _version_scope(self, user_id: int) -> str:
        """Return the acting user's cache version scope.

        This yields ``u:{user_id}:prompts`` so the cache layer stores the
        counter at ``apsor:u:{user_id}:prompts:version``.
        """
        return frequent_prompt_version_scope(user_id, PROMPT_CACHE_SCOPE)

    async def _invalidate(self, user_id: int) -> None:
        """Bump only the acting user's prompt-list version."""
        await self.cache.bump_version(self._version_scope(user_id))


def _normalize(payload: PromptPayload) -> tuple[str, str]:
    """Trim both text fields and reject whitespace-only values.

    Pydantic ``min_length`` alone would let whitespace-only strings through and
    produce the generic validation envelope. Trimming first and raising in the
    service gives the frontend the same stable ``invalid_frequent_prompt`` code
    for both blank and too-short input.
    """
    title = payload.title.strip()
    prompt_text = payload.prompt_text.strip()
    if not title or not prompt_text:
        raise InvalidFrequentPromptError("A frequent prompt title and prompt text are required.")
    return title, prompt_text


def _list_schema(
    rows: list[FrequentlyUsedPromptModel],
) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
    resources = [FrequentlyUsedPromptReadSchema.model_validate(row) for row in rows]
    return ListResponseSchema[FrequentlyUsedPromptReadSchema](
        total_results=len(resources),
        start_index=1,
        items_per_page=len(resources),
        resources=resources,
    )


__all__ = [
    "FREQUENT_PROMPT_CACHE_TTL_SECONDS",
    "MAX_FREQUENT_PROMPTS",
    "FrequentlyUsedPromptService",
]
