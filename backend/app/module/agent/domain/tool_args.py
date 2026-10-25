"""Validated argument models for every agent tool."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ToolArgs(BaseModel):
    """Base class: reject unknown model arguments instead of ignoring them."""

    model_config = ConfigDict(extra="forbid")


class SearchKnowledgeArgs(_ToolArgs):
    """Arguments for hybrid archive search."""

    query: str = Field(min_length=1, max_length=200)
    result_number: int = Field(default=8, ge=1, le=20)
    include_history: bool = False


class ReadFileArgs(_ToolArgs):
    """Arguments for a bounded file chunk window."""

    file_id: int = Field(gt=0)
    chunk: int = Field(default=1, ge=1)
    chunk_range: int = Field(default=1, ge=0, le=25)


class ReadTimelineArgs(_ToolArgs):
    """Arguments for the sparse timeline."""

    year: int = Field(ge=1970, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    day_range: int = Field(default=7, ge=1, le=366)
    include_history: bool = False


class ReadPathArgs(_ToolArgs):
    """Arguments for listing one library path."""

    path: str = Field(default="/", min_length=1, max_length=1024)
    path_depth: int = Field(default=2, ge=1, le=10)
    fuzzy_search: str | None = Field(default=None, max_length=128)


class ReadMemoryArgs(_ToolArgs):
    """Arguments for reading a memory and its chain."""

    memory_id: int = Field(gt=0)
    memory_range: int = Field(default=2, ge=0, le=10)
    trace_history: bool = True


class SaveMemoryArgs(_ToolArgs):
    """Arguments for an explicitly confirmed memory write."""

    content: str = Field(min_length=1, max_length=8000)
    supersedes: list[int] = Field(default_factory=list, max_length=50)
    occurred_at: datetime | None = None
    user_confirmed: bool = Field(
        default=False,
        description=(
            "Legacy model-supplied hint. It never authorizes a write; the backend "
            "records an explicit human approval before executing save_memory."
        ),
    )


class PresentResourceArgs(_ToolArgs):
    """Arguments for a viewer card."""

    resource_type: Literal["file", "memory"]
    resource_id: int = Field(gt=0)
    chunk: int | None = Field(default=None, ge=1)


class WebSearchArgs(_ToolArgs):
    """Arguments for one public web search."""

    # max_results 上限 10、domain 清單各 10 筆：單次搜尋不可淹沒 context window，
    # 也不可讓 provider 收到過大的 filter 清單。query 上限 400 字元足以表達查詢，
    # 同時避免模型把整段私有內容塞進 URL/查詢字串。
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"
    include_domains: list[str] = Field(default_factory=list, max_length=10)
    exclude_domains: list[str] = Field(default_factory=list, max_length=10)


class WebFetchArgs(_ToolArgs):
    """Arguments for fetching one public http(s) URL."""

    # max_chars 限制 1,000–20,000：至少足以讀一段文章，又不會讓單一 tool result
    # 超過 agent 的結果預算。URL 長度上限與 WebUrlSafety 的 1–2048 保持一致。
    url: str = Field(min_length=1, max_length=2048)
    max_chars: int = Field(default=12_000, ge=1_000, le=20_000)
