"""Persistence contract for ordered custom system prompt sections."""

from datetime import datetime
from typing import Protocol

from app.module.agent.domain.system_prompt_domain import SystemPromptSection


class SystemPromptRepositoryProtocol(Protocol):
    """CRUD and reordering over owner-authored prompt sections."""

    async def list_sections(self) -> list[SystemPromptSection]: ...

    async def get_section(self, section_id: int) -> SystemPromptSection | None: ...

    async def next_sort_order(self) -> int:
        """Return ``max(sort_order) + 10`` so appends leave manual gaps."""
        ...

    async def create_section(
        self,
        *,
        title: str,
        body: str,
        sort_order: int,
        now: datetime,
    ) -> SystemPromptSection: ...

    async def update_section(
        self,
        section_id: int,
        *,
        title: str,
        body: str,
        sort_order: int,
        now: datetime,
    ) -> SystemPromptSection | None: ...

    async def delete_section(self, section_id: int) -> bool: ...

    async def reorder_sections(
        self,
        section_ids: list[int],
        *,
        now: datetime,
    ) -> list[SystemPromptSection]:
        """Rewrite ``sort_order`` in one transaction.

        ``section_ids`` must contain every existing section exactly once. The
        repository raises ``ValueError`` when the set is incomplete or contains
        duplicates; the service translates that into the stable 422 domain
        error. 驗證必須在 ``FOR UPDATE`` 鎖住全部列之後進行，否則兩個並行
        reorder 可能在讀取與寫入之間插入新 section，造成遺漏。
        """
        ...

    async def clear_sections(self) -> None: ...

    async def list_builtin_overrides(self) -> dict[str, SystemPromptSection]: ...

    async def upsert_builtin_override(
        self,
        *,
        key: str,
        title: str,
        body: str,
        now: datetime,
    ) -> SystemPromptSection: ...

    async def clear_builtin_overrides(self) -> None: ...


__all__ = ["SystemPromptRepositoryProtocol"]
