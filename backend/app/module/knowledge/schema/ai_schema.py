"""Schemas for AI answers and citations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CitationKind = Literal["file", "memory", "summary"]


class AskRequestSchema(BaseModel):
    """A question answered from retrieved knowledge."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=2000)
    result_number: int = Field(default=4, ge=1, le=10)


class CitationSchema(BaseModel):
    """One retrievable source behind an answer."""

    model_config = ConfigDict(frozen=True)

    kind: CitationKind
    label: str
    excerpt: str
    time: datetime
    cited: bool
    file_id: int | None = None
    chunk: int | None = None
    raw_file_path: str | None = None
    memory_id: int | None = None
    memory_summary_id: int | None = None


class AskResponseSchema(BaseModel):
    """The answer plus every source the retrieval stage supplied."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[CitationSchema]
    model: str
    usage: dict[str, int]
    elapsed_ms: int
    retrieved: dict[str, int]
    search_queries: list[str]


class AiStatusSchema(BaseModel):
    """Configuration state for the AI and vector paths."""

    model_config = ConfigDict(frozen=True)

    configured: bool
    model: str
    provider: str
    embedding_provider: str
    embedding_model: str
    vector_enabled: bool
