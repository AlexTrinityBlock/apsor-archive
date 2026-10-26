"""Response schemas for web search and web fetch.

These are DTOs: the agent tool layer renders them into XML, and the service
stores ``model_dump(mode="json")`` in the cache. They deliberately contain no
configuration or credential fields.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WebSearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    content: str
    score: float | None = None


class WebSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    query: str
    results: list[WebSearchHit] = Field(default_factory=list)
    elapsed_ms: int
    truncated: bool = False
    cached: bool = False
    retrieved_at: datetime


class WebFetchResponse(BaseModel):
    """One full page or one line-bounded slice of it.

    ``truncated`` describes this response (the slice is not the complete
    document), while ``source_truncated`` describes the cached full document
    (the provider or the service cache cap cut it). The pagination fields have
    defaults so a cache payload written before pagination still validates.
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    url: str
    content: str
    elapsed_ms: int
    truncated: bool = False
    cached: bool = False
    retrieved_at: datetime
    offset: int = 1
    limit: int = 200
    page: int = 1
    total_pages: int = 1
    total_lines: int = 0
    total_chars: int = 0
    returned_lines: int = 0
    has_more: bool = False
    next_offset: int | None = None
    next_page: int | None = None
    source_truncated: bool = False
