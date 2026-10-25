"""Schemas for files, chunks, and the File Library tree listing."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IngestJobStatus = Literal[
    "queued",
    "parsing",
    "chunking",
    "embedding",
    "summarizing",
    "ready",
    "failed",
]
IngestSourceKind = Literal["upload", "text"]

# Pydantic 解析階段的內容長度上限；service 的 max_text_bytes（2 MiB）仍是最終 byte 限制。
MAX_TEXT_CONTENT_CHARS = 2_000_000


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
    has_original: bool
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
    content: str = Field(min_length=1, max_length=MAX_TEXT_CONTENT_CHARS)
    occurred_at: datetime | None = None


class FileTextUpdateSchema(BaseModel):
    """更新既有 Markdown 檔案內容；expected_version 用於樂觀鎖。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_TEXT_CONTENT_CHARS)
    expected_version: int = Field(ge=1)


class IngestJobSchema(BaseModel):
    """Durable ingestion job state and progress for one file path."""

    model_config = ConfigDict(frozen=True)

    id: int
    file_id: int | None
    source_kind: IngestSourceKind
    path: str
    file_name: str
    mime_type: str
    size_bytes: int
    occurred_at: datetime | None
    status: IngestJobStatus
    stage: str | None
    progress_pct: int
    chunks_total: int | None
    chunks_embedded: int | None
    error_code: str | None
    error_detail: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class IngestJobListSchema(BaseModel):
    """A page of active and recent ingestion jobs."""

    model_config = ConfigDict(frozen=True)

    total_results: int
    jobs: list[IngestJobSchema]


class FolderCreateSchema(BaseModel):
    """Create one folder and any missing ancestors.

    Empty values reach the service so they become the stable ``invalid_path``
    domain error instead of a generic schema-validation error.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=1024)


class FileMoveSchema(BaseModel):
    """Move one current file to another logical path."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=1024)


class FileCopySchema(BaseModel):
    """Copy one current file to a new logical path."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=1024)


class FileRenameSchema(BaseModel):
    """Rename one current file without changing its parent folder."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=255)


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
    has_original: bool
    update_time: datetime


class PathListingSchema(BaseModel):
    """The response of the read_path tool."""

    model_config = ConfigDict(frozen=True)

    path: str
    fuzzy_search: str | None
    directories: list[DirectorySchema]
    files: list[PathFileSchema]


class FileListSchema(BaseModel):
    """A small collection envelope for browse screens."""

    model_config = ConfigDict(frozen=True)

    total_results: int
    files: list[PathFileSchema]
