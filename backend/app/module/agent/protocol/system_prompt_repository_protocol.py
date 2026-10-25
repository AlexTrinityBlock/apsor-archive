"""Persistence contract for ordered system prompt sections."""

from datetime import datetime
from typing import Protocol

from app.module.agent.domain.system_prompt_domain import SystemPromptSection


class SystemPromptRepositoryProtocol(Protocol):
    """CRUD and reordering over every prompt section."""

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
        error. Validation happens after ``FOR UPDATE`` locks every row so two
        concurrent reorders cannot insert or omit a section between the read and
        the write.
        """
        ...

    async def replace_with_defaults(
        self,
        defaults: list[dict[str, str]],
        *,
        now: datetime,
    ) -> list[SystemPromptSection]:
        """Delete every row and insert the seeded defaults in one transaction."""
        ...


__all__ = ["SystemPromptRepositoryProtocol"]
