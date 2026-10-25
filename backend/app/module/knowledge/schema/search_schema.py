"""Schemas for hybrid knowledge search."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
