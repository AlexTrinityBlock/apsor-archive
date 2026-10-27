"""Consumer-owned protocols for the knowledge and web-research services used by tools."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.module.knowledge.schema.file_schema import FileChunksSchema, FileSchema, PathListingSchema
from app.module.knowledge.schema.memory_schema import (
    MemoryReadSchema,
    MemorySaveSchema,
    MemorySchema,
)
from app.module.knowledge.schema.search_schema import SearchResponseSchema
from app.module.knowledge.schema.timeline_schema import TimelineResponseSchema
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchResponse,
)


class SearchToolServiceProtocol(Protocol):
    async def search(
        self,
        query: str,
        *,
        result_number: int,
        include_history: bool,
    ) -> SearchResponseSchema: ...


class FileToolServiceProtocol(Protocol):
    async def get_file(self, file_id: int) -> FileSchema: ...

    async def read_chunks(
        self,
        file_id: int,
        *,
        chunk: int,
        chunk_range: int,
    ) -> FileChunksSchema: ...

    async def list_path(
        self,
        *,
        path: str,
        path_depth: int,
        fuzzy_search: str | None,
    ) -> PathListingSchema: ...


class MemoryToolServiceProtocol(Protocol):
    async def read_memory(
        self,
        memory_id: int,
        *,
        memory_range: int,
        trace_history: bool,
    ) -> MemoryReadSchema: ...

    async def save_memory(
        self,
        *,
        content: str,
        supersedes: list[int],
        occurred_at: datetime | None,
        source: str,
        auto_summary: bool = True,
    ) -> MemorySaveSchema: ...

    async def deprecate_memories(
        self,
        memory_ids: list[int],
        *,
        reason: str | None = None,
    ) -> list[MemorySchema]: ...


class TimelineToolServiceProtocol(Protocol):
    async def get_timeline(
        self,
        *,
        year: int,
        month: int,
        day: int,
        day_range: int,
        include_history: bool,
    ) -> TimelineResponseSchema: ...


class WebResearchServiceProtocol(Protocol):
    """The two read-only web capabilities the agent tools depend on.

    This is a consumer-owned protocol: the agent slice only declares the shape it
    needs, the real implementation is provided by ``app.module.web_research`` and
    satisfies it structurally, so agent never imports the whole web service
    implementation. ``search_depth`` reuses the tool argument Literal directly so
    the provider implementation and the tool layer share one definition of
    "basic / advanced".
    """

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        search_depth: Literal["basic", "advanced"],
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> WebSearchResponse: ...

    async def fetch(
        self,
        url: str,
        *,
        page: int | None = None,
        offset: int | None = None,
    ) -> WebFetchResponse: ...


@dataclass(frozen=True)
class AgentToolServices:
    """The live services one tool execution may use."""

    search_service: SearchToolServiceProtocol
    file_service: FileToolServiceProtocol
    memory_service: MemoryToolServiceProtocol
    timeline_service: TimelineToolServiceProtocol
    web_research_service: WebResearchServiceProtocol


class ToolServiceScopeProtocol(Protocol):
    """Open a short-lived session-backed service bundle for one tool call."""

    def __call__(self) -> AbstractAsyncContextManager[AgentToolServices]: ...
