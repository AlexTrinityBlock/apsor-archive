"""Consumer-defined contract for the summary service."""

from typing import Protocol

from app.module.knowledge.schema.memory_schema import SummarySchema


class SummaryServiceProtocol(Protocol):
    """The memory service only needs the automatic-summary trigger."""

    async def maybe_auto_summary(self) -> SummarySchema | None: ...
