"""Consumer-defined contract for hybrid search."""

from typing import Protocol

from app.module.knowledge.schema.search_schema import SearchResponseSchema


class SearchServiceProtocol(Protocol):
    async def search(
        self,
        query: str,
        *,
        result_number: int,
        include_history: bool,
    ) -> SearchResponseSchema: ...
