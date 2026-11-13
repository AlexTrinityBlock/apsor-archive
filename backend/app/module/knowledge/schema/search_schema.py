"""Schemas for hybrid knowledge search."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MatchSource = Literal["text", "vector"]


class SearchStatsSchema(BaseModel):
    """Diagnostics that make the 2 + 2 dedup visible to the UI."""

    model_config = ConfigDict(frozen=True)

    text_candidates: int
    vector_candidates: int
    merged: int
    deduplicated: int
    chunks_scanned: int
    terms: list[str]
    # Conversation-history diagnostics. They default to zero so a cached
    # payload written before the history lane existed still validates.
    history_vector_candidates: int = 0
    history_selected: int = 0


class FileSearchResultSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_id: int
    raw_file_path: str
    file_name: str
    update_time: datetime
    chunk: int
    chunk_id: int
    content: str
    is_current: bool
    score: float
    matched_by: list[MatchSource]


class MemorySearchResultSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: int
    title: str
    update_time: datetime
    content: str
    status: str
    score: float
    matched_by: list[MatchSource]


class SummarySearchResultSchema(BaseModel):
    """A summary hit; it is a compressed view, not the original memories."""

    model_config = ConfigDict(frozen=True)

    memory_summary_id: int
    update_time: datetime
    content: str
    period_start: datetime
    period_end: datetime
    themes: list[str]
    memory_count: int
    source_memory_ids: list[int]
    score: float
    matched_by: list[MatchSource]


class HistorySearchResultSchema(BaseModel):
    """One 256-character window from a past conversation message.

    ``entry_id`` is the stable id used by the agent's ``history_message`` tool.
    The window is raw text; the XML envelope and id are applied at tool render
    time so the index itself contains no markup.
    """

    model_config = ConfigDict(frozen=True)

    entry_id: int
    chunk_id: int
    chunk: int
    content: str
    score: float
    matched_by: list[MatchSource]
    vector_score: float | None = None
    text_score: float | None = None


class SearchResponseSchema(BaseModel):
    """The search_knowledge tool result."""

    model_config = ConfigDict(frozen=True)

    query: str
    result_number: int
    include_history: bool
    elapsed_ms: int
    stats: SearchStatsSchema
    file_results: list[FileSearchResultSchema]
    memory_results: list[MemorySearchResultSchema]
    summary_results: list[SummarySearchResultSchema]
    history_results: list[HistorySearchResultSchema] = Field(default_factory=list)
