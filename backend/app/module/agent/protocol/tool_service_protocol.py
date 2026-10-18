"""Consumer-owned protocols for the knowledge and media services used by tools."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.module.knowledge.schema.file_schema import FileChunksSchema, FileSchema, PathListingSchema
from app.module.knowledge.schema.memory_schema import MemoryReadSchema, MemorySaveSchema
from app.module.knowledge.schema.search_schema import SearchResponseSchema
from app.module.knowledge.schema.timeline_schema import TimelineResponseSchema
from app.module.media.schema.media_schema import MediaSchema, MediaSearchResponseSchema


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


class MediaToolServiceProtocol(Protocol):
    async def get(self, media_id: int) -> MediaSchema: ...

    async def search_text(
        self,
        *,
        query: str,
        limit: int,
    ) -> MediaSearchResponseSchema: ...


@dataclass(frozen=True)
class AgentToolServices:
    """The live services one tool execution may use."""

    search_service: SearchToolServiceProtocol
    file_service: FileToolServiceProtocol
    memory_service: MemoryToolServiceProtocol
    timeline_service: TimelineToolServiceProtocol
    media_service: MediaToolServiceProtocol


class ToolServiceScopeProtocol(Protocol):
    """Open a short-lived session-backed service bundle for one tool call."""

    def __call__(self) -> AbstractAsyncContextManager[AgentToolServices]: ...
