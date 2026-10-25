"""Consumer-owned protocols for the knowledge and web-research services used by tools."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.module.knowledge.schema.file_schema import FileChunksSchema, FileSchema, PathListingSchema
from app.module.knowledge.schema.memory_schema import MemoryReadSchema, MemorySaveSchema
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

    這是 consumer-owned protocol：agent slice 只宣告自己需要的形狀，實際實作由
    ``app.module.web_research`` 提供並以結構性型別滿足，所以 agent 不需要 import
    整個 web service 實作。``search_depth`` 直接沿用工具參數的 Literal，讓
    provider 實作與工具層對「basic / advanced」有同一個定義。
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

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse: ...


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
