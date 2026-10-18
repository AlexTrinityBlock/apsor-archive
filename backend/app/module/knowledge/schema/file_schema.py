"""Schemas for files, chunks, and the File Library tree listing."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileSchema(BaseModel):
    """File metadata returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: int
    raw_file_path: str
    file_name: str
    extension: str
    mime_type: str
    size_bytes: int
    version: int
    supersedes_file_id: int | None
    is_current: bool
    total_chunks: int
    ai_summary: str | None
    ai_tags: list[str]
    document_type: str
    extraction_method: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FileTextCreateSchema(BaseModel):
    """Create a text file directly; used by the UI and tests."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ChunkSchema(BaseModel):
    """One chunk in a read window."""

    model_config = ConfigDict(frozen=True)

    chunk: int
    content: str
    char_count: int
    token_count: int
    is_current: bool


class FileChunksSchema(BaseModel):
    """The response of the read_file tool."""

    model_config = ConfigDict(frozen=True)

    file_id: int
    raw_file_path: str
    file_name: str
    update_time: datetime
    total_chunks: int
    chunk_start: int
    chunk_end: int
    chunks: list[ChunkSchema]


class DirectorySchema(BaseModel):
    """One directory in a path listing."""

    model_config = ConfigDict(frozen=True)

    path: str
    name: str
    depth: int


class PathFileSchema(BaseModel):
    """One file in a path listing."""

    model_config = ConfigDict(frozen=True)

    file_id: int
    raw_file_path: str
    file_name: str
    total_chunks: int
    size_bytes: int
    update_time: datetime


class PathListingSchema(BaseModel):
    """The response of the read_path tool."""

    model_config = ConfigDict(frozen=True)

    path: str
    fuzzy_search: str | None
    directories: list[DirectorySchema]
    files: list[PathFileSchema]


class TreeNodeSchema(BaseModel):
    """One node in the unified tree."""

    model_config = ConfigDict(frozen=True)

    id: int
    parent_id: int | None
    path: str
    name: str
    kind: Literal["folder", "file"]
    file_id: int | None
    depth: int
    is_current: bool
    superseded_by_id: int | None
    deleted_at: datetime | None
    update_time: datetime


class TreeSchema(BaseModel):
    """Flat nodes for the frontend tree layout engine."""

    model_config = ConfigDict(frozen=True)

    root: str
    depth: int
    include_history: bool
    total: int
    truncated: bool
    nodes: list[TreeNodeSchema]


class FileListSchema(BaseModel):
    """A small collection envelope for browse screens."""

    model_config = ConfigDict(frozen=True)

    total_results: int
    files: list[PathFileSchema]
