"""Manage ordered owner-authored system prompt sections.

The list is read before every conversation is created, so it is cached under the
dedicated ``system_prompts`` version scope. Writes bump only that scope; the
global archive index version stays untouched and archive search caches survive a
prompt edit.
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
    SystemPromptBuiltinSectionSchema,
    SystemPromptBuiltinUpdateSchema,
    SystemPromptSectionCreateSchema,
    SystemPromptSectionReadSchema,
    SystemPromptSectionUpdateSchema,
)
from app.module.agent.service.system_prompt import (
    BUILTIN_PROMPT_KEYS,
    prompt_sections,
)
from app.shared.time import utcnow
from app.shared.types.list_response import ListResponseSchema

SYSTEM_PROMPT_CACHE_SCOPE = "system_prompts"
SYSTEM_PROMPT_CACHE_TTL_SECONDS = 30
SYSTEM_PROMPT_CACHE_NAMESPACE = "system_prompts"


def _cache_key(version: int) -> str:
    """Build a versioned cache key without importing another slice's helper.

    Key 形狀固定為 ``apsor:<version>:system_prompts:<sha256>``。版本號一旦
    bump，舊 key 自然不會再被命中，因此不必逐筆刪除快取，也不會影響 archive
    index 或 provider registry 的 scope。
    """
    digest = hashlib.sha256(SYSTEM_PROMPT_CACHE_NAMESPACE.encode("utf-8")).hexdigest()[:24]
    return f"apsor:{version}:{SYSTEM_PROMPT_CACHE_NAMESPACE}:{digest}"


class SystemPromptService:
    """Validate, persist, reorder, and cache owner-authored prompt sections."""

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
        # 30 秒 TTL 是第二道保險：即使版本遞增機制失效（例如外部程序直接寫
        # DB），清單仍會在短時間內自動回到資料庫最新狀態。
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response

    async def get_active_sections(
        self,
    ) -> tuple[list[SystemPromptSection], list[dict[str, str]]]:
        """Return custom sections plus the effective ordered built-ins.

        Custom sections keep their drag order and render first. Built-in
        sections follow in canonical order, using the owner's override when one
        exists and the Python default otherwise. Empty bodies are skipped so a
        directly-edited row can never inject an empty provider heading.
        """
        response = await self.list_sections()
        resources = sorted(
            response.resources,
            key=lambda item: (item.sort_order, item.id),
        )
        custom = [
            SystemPromptSection(
                id=item.id,
                title=item.title,
                body=item.body,
                sort_order=item.sort_order,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in resources
            if item.body.strip()
        ]
        built_in = [
            {"name": item.key, "title": item.title, "content": item.body}
            for item in (await self.list_builtin_sections()).resources
            if item.body.strip()
        ]
        return custom, built_in

    async def list_builtin_sections(
        self,
    ) -> ListResponseSchema[SystemPromptBuiltinSectionSchema]:
        """Return all four built-ins, whether or not each has an override."""
        overrides = await self.repository.list_builtin_overrides()
        defaults = {section["name"]: section for section in prompt_sections()}
        resources: list[SystemPromptBuiltinSectionSchema] = []
        for key in BUILTIN_PROMPT_KEYS:
            default = defaults[key]
            override = overrides.get(key)
            resources.append(
                SystemPromptBuiltinSectionSchema(
                    key=key,
                    title=default["title"],
                    body=override.body if override is not None else default["content"],
                    customized=override is not None,
                    updated_at=override.updated_at if override is not None else None,
                )
            )
        return ListResponseSchema[SystemPromptBuiltinSectionSchema](
            total_results=len(resources),
            start_index=1,
            items_per_page=len(resources),
            resources=resources,
        )

    async def update_builtin_section(
        self,
        key: str,
        payload: SystemPromptBuiltinUpdateSchema,
    ) -> ListResponseSchema[SystemPromptBuiltinSectionSchema]:
        """Store one built-in override; titles and order remain canonical."""
        if key not in BUILTIN_PROMPT_KEYS:
            raise AgentSystemPromptNotFoundError(key)
        body = payload.body.strip()
        if not body:
            raise AgentInvalidSystemPromptError("A system prompt body is required.")
        defaults = {section["name"]: section for section in prompt_sections()}
        await self.repository.upsert_builtin_override(
            key=key,
            title=defaults[key]["title"],
            body=body,
            now=utcnow(),
        )
        await self.cache.bump_version(SYSTEM_PROMPT_CACHE_SCOPE)
        return await self.list_builtin_sections()

    async def reset_builtin_sections(
        self,
    ) -> ListResponseSchema[SystemPromptBuiltinSectionSchema]:
        """Remove every override, restoring the pristine built-in prompt."""
        await self.repository.clear_builtin_overrides()
        await self.cache.bump_version(SYSTEM_PROMPT_CACHE_SCOPE)
        return await self.list_builtin_sections()

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
            # Repository 只回報「集合不吻合」這個結構性問題；轉成 agent
            # slice 的穩定錯誤碼，避免 ValueError 變成 500。
            raise AgentInvalidSystemPromptError(str(exc)) from exc
        return await self._write_result()

    async def reset_sections(self) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Delete every custom section and return the resulting empty list."""
        await self.repository.clear_sections()
        return await self._write_result()

    async def _write_result(self) -> ListResponseSchema[SystemPromptSectionReadSchema]:
        """Invalidate the scoped cache, then read the committed rows back.

        Bump 只遞增 ``system_prompts`` 版本，不動全站 index。寫入完成後重新
        呼叫 ``list_sections``，確保回傳的是資料庫實際狀態（包含 trim、
        identity 與 sort_order 調整後的結果），而不是自行拼湊的區域副本。
        """
        await self.cache.bump_version(SYSTEM_PROMPT_CACHE_SCOPE)
        return await self.list_sections()


def _normalize(*, title: str, body: str) -> tuple[str, str]:
    """Trim both fields and reject whitespace-only values.

    只靠 Pydantic 的 ``min_length`` 會讓「只有空白」變成通用 validation
    envelope；先 trim 再由 service 拋出 ``agent_invalid_system_prompt``，
    前端才能用同一個錯誤碼處理空白與長度不足。
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
