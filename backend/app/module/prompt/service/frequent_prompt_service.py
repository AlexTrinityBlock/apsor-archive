"""Editable frequently used prompts shown on the empty chat page.

The list is tiny (at most 20 rows) but read on every new chat, so it is cached
under the dedicated ``prompts`` version scope. Writes bump only that scope: the
global index version is reserved for archive content and embeddings.
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
from app.module.prompt.service.frequent_prompt_cache_key import frequent_prompt_cache_key
from app.shared.time import utcnow
from app.shared.types.list_response import ListResponseSchema

MAX_FREQUENT_PROMPTS = 20
FREQUENT_PROMPT_CACHE_TTL_SECONDS = 60
PROMPT_CACHE_NAMESPACE = "frequent_prompts"

PromptPayload = FrequentlyUsedPromptCreateSchema | FrequentlyUsedPromptUpdateSchema


class FrequentlyUsedPromptService:
    """Validate, persist, and cache the owner-editable prompt shortcuts."""

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

    async def list_prompts(self) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
        """Return every prompt in ``sort_order, id`` order, using the cache first.

        快取 key 由「prompts scope 的版本號 + 固定 namespace」組成。寫入時
        bump 版本號即可讓舊 key 自然失效，不必逐筆刪除，也不會影響全站
        index 快取。
        """
        version = await self.cache.get_version("prompts")
        key = frequent_prompt_cache_key(version, PROMPT_CACHE_NAMESPACE)
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return ListResponseSchema[FrequentlyUsedPromptReadSchema].model_validate(cached)

        rows = await self.repository.list_all()
        response = _list_schema(rows)
        # 即使版本遞增機制失效，60 秒 TTL 也會讓清單自動回到資料庫最新狀態。
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response

    async def create_prompt(
        self,
        payload: FrequentlyUsedPromptCreateSchema,
    ) -> FrequentlyUsedPromptReadSchema:
        title, prompt_text = _normalize(payload)
        # 20 筆上限是業務規則，不是資料庫 constraint；先計數再寫入，避免
        # 使用者透過 UI 以外的呼叫不斷新增。此檢查在同一交易內完成。
        count = await self.repository.count_all()
        if count >= MAX_FREQUENT_PROMPTS:
            raise TooManyFrequentPromptsError(MAX_FREQUENT_PROMPTS)

        row = await self.repository.add(
            title=title,
            prompt_text=prompt_text,
            sort_order=payload.sort_order,
            now=utcnow(),
        )
        # 寫入成功後只失效 prompts scope，讓下一次 GET 重新建立快取。
        await self.cache.bump_version("prompts")
        return FrequentlyUsedPromptReadSchema.model_validate(row)

    async def update_prompt(
        self,
        prompt_id: int,
        payload: FrequentlyUsedPromptUpdateSchema,
    ) -> FrequentlyUsedPromptReadSchema:
        title, prompt_text = _normalize(payload)
        row = await self.repository.update(
            prompt_id,
            title=title,
            prompt_text=prompt_text,
            sort_order=payload.sort_order,
            now=utcnow(),
        )
        if row is None:
            raise FrequentPromptNotFoundError(prompt_id)

        await self.cache.bump_version("prompts")
        return FrequentlyUsedPromptReadSchema.model_validate(row)

    async def reorder_prompts(
        self,
        prompt_ids: list[int],
    ) -> ListResponseSchema[FrequentlyUsedPromptReadSchema]:
        """Replace the complete shortcut order atomically.

        缺少、重複或未知的 id 都代表整份順序不一致；repository 只回報集合
        不符，這裡轉成穩定的 ``invalid_frequent_prompt``，避免變成 500。
        回傳的是剛 flush 的資料庫順序，不讀舊快取；bump 版本讓下一次 GET
        重新建立快照。
        """
        try:
            rows = await self.repository.reorder(prompt_ids, now=utcnow())
        except ValueError as exc:
            raise InvalidFrequentPromptError(str(exc)) from exc

        await self.cache.bump_version("prompts")
        return _list_schema(rows)

    async def delete_prompt(self, prompt_id: int) -> None:
        """Hard-delete one prompt; the identity sequence is never rewound."""
        deleted = await self.repository.delete(prompt_id)
        if not deleted:
            raise FrequentPromptNotFoundError(prompt_id)

        await self.cache.bump_version("prompts")


def _normalize(payload: PromptPayload) -> tuple[str, str]:
    """Trim both text fields and reject whitespace-only values.

    空白字串若只靠 Pydantic 的 ``min_length``，會得到通用的 validation
    envelope；先 trim 再由 service 拋出 ``invalid_frequent_prompt``，前端才能
    用同一個穩定錯誤碼處理「只有空白」與「長度不足」。
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
