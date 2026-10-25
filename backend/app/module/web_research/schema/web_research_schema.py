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
    model_config = ConfigDict(frozen=True)

    provider: str
    url: str
    content: str
    elapsed_ms: int
    truncated: bool = False
    cached: bool = False
    retrieved_at: datetime
