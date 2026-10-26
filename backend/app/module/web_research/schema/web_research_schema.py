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
    """One server-defined page of a cached full document.

    ``page_chars`` is the body length of this page and ``total_chars`` is the
    cached document length after normalization and wrapping. ``truncated``
    describes this response (more pages exist or the source was clipped), while
    ``source_truncated`` describes the cached full document (the provider or the
    service cache cap cut it).

    Unknown keys are ignored deliberately: a cache payload written by the older
    line-offset implementation still validates because Pydantic ignores extra
    fields by default. Do not set ``extra="forbid"`` here.
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    url: str
    content: str
    elapsed_ms: int
    truncated: bool = False
    cached: bool = False
    retrieved_at: datetime
    page: int = 1
    total_pages: int = 1
    page_chars: int = 0
    total_chars: int = 0
    has_more: bool = False
    next_page: int | None = None
    source_truncated: bool = False
